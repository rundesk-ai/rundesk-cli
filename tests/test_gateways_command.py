"""`rundesk gateways` — what a person types, and what a person is shown.

Driven through `self.rundesk(...)`, so the real parser and the real dispatch answer every case. A
case that called `cmd_gateways` directly would prove the module and not the command: the sub-verb it
registered, the flag it spelled, and the exit code the shell reads are exactly the parts a direct
call skips.

**No case here may reach `launchctl`, and no case here may write into `~/Library/LaunchAgents`.**
That is not a preference. `release.Asking` and `update.Fetching` are replaced in their suites so
that nothing leaves the machine, and a case that forgot would fail loudly on somebody's network.
This seam has no such safety net: the real supervisor would answer a case perfectly well, in the
owner's own login session, booting out jobs that keep real work running. So `tests/support.py`
hands every command a stand-in by default, replaces `job.Launchd` with something that raises, and
sends every plist a command writes into the scratch root — and then proves the owner's login items
are exactly as they were found, after every case in every suite.

**A running gateway here is a real `flock`**, taken on a second descriptor by the case itself. The
kernel is what `standing` asks, and a stand-in for a lock would prove nothing about the one property
this whole design exists to have: that a gateway which was killed outright never looks alive.

**And a gateway that has to be *stopped* is a real process**, started by the case itself and by
nothing else. A signal that lands is the whole of what those cases prove, so there is nothing to
stand in for: a mock would be asserting that this suite can call a function. Every one of them
signals only the pid it started, never a group and never a number it read somewhere, and takes that
process away again however the case ended.

Run directly: `python3 tests/test_gateways_command.py`
"""

import contextlib
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from typing import List, Optional, Tuple
from unittest import mock

import support
from rundesk.agents import directory
from rundesk.commands import gateways
from rundesk.core import paths
from rundesk.exits import FAILED, OK, USAGE
from rundesk.gateways import job, standing
from rundesk.utils import files, logs, programs


def ran(code: Optional[int] = 0, out: str = "", err: str = "",
        trouble: Optional[str] = None) -> programs.Ran:
    """One answer from a supervisor, in the shape `utils.programs` hands back."""
    return support.ran(code, out, err, trouble)


#: An agent named something `agents` allows and a launchd label can never carry.
#:
#: **The two rules really are different, and that is the whole of the defect these cases cover.**
#: `agents add "my agent"` succeeds, `gateways run "my agent"` is a supported verb, and
#: `job.IN_A_LABEL` refuses the name — so a gateway can be started for an agent that can never have
#: a job, and every stopping verb used to refuse the name before it had even asked whether one was
#: running.
UNLABELABLE = "my agent"

#: A real gateway, for the cases whose whole point is that a signal has to land on one.
#:
#: It does the two things `host` does that those cases turn on and nothing else: it takes the
#: agent's `flock` and writes the record beside it, so `standing` answers `ONLINE` with its pid.
#: The paths are handed in rather than derived here, so this carries no second opinion about what
#: either file is called.
#:
#: `ignoring` makes it deaf to `SIGTERM`, which is the one gateway `--force` exists for — the state
#: where a graceful stop waits out its whole window and a forced one does not.
A_REAL_GATEWAY = """\
import fcntl, json, os, signal, sys, time

lock, record, how = sys.argv[1], sys.argv[2], sys.argv[3]
if how == "ignoring":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
held = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
with open(record + ".being-written", "w") as writing:
    json.dump({"name": "a real gateway", "pid": os.getpid(), "version": "0.0.0",
               "started_at": "now", "beat_at": "now", "since_boot": time.monotonic()}, writing)
os.rename(record + ".being-written", record)
while True:
    time.sleep(0.05)
"""


class ALaunchdThatReallyStarts(support.ASupervisor):
    """A stand-in whose bootstrap — or kickstart — really does start something.

    **Because a job launchd accepted is not a gateway that started**, and the command has to be able
    to tell those apart. A stand-in that only answered `0` could never show the difference, so this
    one claims the agent's name the way a gateway does: an exclusive `flock` on the same file, held
    on a descriptor of its own, released when the job is booted out.

    `on` is which verb starts it, which is how a case drives the two paths apart — a gateway that
    comes up on its own after a bootstrap, and one that only comes up once it has been kicked
    through a throttle.

    **`kill` drops the name as well as `bootout`**, because that is what the real one does: a
    `SIGKILL`ed process loses its `flock` the moment the kernel closes its descriptors, which is
    exactly why the `bootout --wait` behind a `--force` returns at once.
    """

    #: Every verb after which nothing is holding the agent's name any more.
    LETS_GO = ("bootout", "kill")

    def __init__(self, at: Path, name: str = "cole", on: Tuple[str, ...] = ("bootstrap",),
                 **answers: programs.Ran) -> None:
        super().__init__(**answers)
        self.at = at
        self.name = name
        self.on = on
        self.up = False
        self.held = contextlib.ExitStack()

    def answer(self, verb: str, what: str) -> programs.Ran:
        said = super().answer(verb, what)
        if verb in self.on and not self.up:
            self.held.enter_context(standing.holding(self.at))
            standing.write_record(self.at, self.name, "0.0.0")
            self.up = True
        if verb in self.LETS_GO and self.up:
            self.let_go()
        return said

    def let_go(self) -> None:
        """Drop the name, the way a gateway does when its job is taken back."""
        self.held.close()
        self.held = contextlib.ExitStack()
        self.up = False


class WithAnAgent(support.Isolated):
    """A scratch install with one real agent in it, and the means to hold its name."""

    def setUp(self) -> None:
        super().setUp()
        self.at = directory.made("cole", "claude")
        self.label = job.label_for("cole", self.home)
        # Waits are asked rather than slept through, so shortening them changes nothing about what
        # is proved — only how long a case that is waiting for something that will never happen
        # takes to say so. What the product ships is read here, before it is shortened, and
        # asserted in `TheSeamItself`: otherwise every case would be proving the value it set.
        self.as_shipped = {named: getattr(gateways, named)
                           for named in ("ON_ITS_OWN_SECONDS", "CAME_UP_SECONDS",
                                         "WENT_AWAY_SECONDS")}
        for named in self.as_shipped:
            patched = mock.patch.object(gateways, named, 0.05)
            patched.start()
            self.addCleanup(patched.stop)

    def plist(self) -> Path:
        """Where a plist this install writes lands — in the scratch root, never in the owner's."""
        return self.home / "LaunchAgents" / f"{self.label}.plist"

    @contextlib.contextmanager
    def a_running_gateway(self, name: str = "cole"):
        """The agent's name, really held, on a descriptor of this case's own."""
        at = directory.where(name)
        with standing.holding(at):
            standing.write_record(at, name, "0.0.0")
            yield

    def a_real_gateway(self, name: str = "cole", ignoring_sigterm: bool = False) -> int:
        """A process of this case's own, really holding one agent's name. Hands back its pid.

        **Started rather than pretended, because what these cases prove is that a signal lands.**
        A stand-in holding the lock inside this very process could not be signalled at all —
        `utils.programs.stop` refuses this command's own process group, which is the guard that
        stands between a reused pid and a suite killing its own runner.

        Waited for rather than slept after: the case may not go on until the kernel has really
        given the lock away and the record beside it names this process.

        **Watched through the record and never by probing the lock**, which is a difference this
        suite paid for. `standing()` answers by taking a *shared* lock, and a shared lock excludes
        the exclusive one the child is trying to take — so a wait implemented as `standing()` in a
        loop was a wait that could refuse the very thing it was waiting for. It did, on Ubuntu under
        CI load: the child's claim was refused in the microseconds a poll was reading, the child
        died, and the case spent its whole ceiling waiting for a gateway nothing was going to start.
        The record is written by `os.rename` after the lock is held, so a record naming this process
        is proof the claim landed — and reading it takes no lock and refuses nothing.
        """
        at = directory.where(name)
        at.mkdir(parents=True, exist_ok=True)
        started = subprocess.Popen(
            [sys.executable, "-c", A_REAL_GATEWAY, str(at / standing.LOCK),
             str(at / standing.RECORD), "ignoring" if ignoring_sigterm else "asking"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            # A session of its own, exactly as `utils.programs.start` gives a real gateway one —
            # which is what makes it a process group the command may signal, and what keeps this
            # suite's own group out of reach of the signal it is about to ask for.
            start_new_session=True)
        self.addCleanup(self.ended, started)
        self.assertTrue(
            support.waited_until(lambda: self.what_it_recorded(at) == started.pid, 10.0),
            f"the gateway this case started never took {at / standing.LOCK}")
        # Asked once, and only now that the child is already holding the name: a probe cannot refuse
        # a claim that has already landed. This is what keeps the kernel — and not the file the
        # child wrote — as what says a gateway is up.
        self.assertEqual(standing.ONLINE, standing.standing(at).how,
                         f"the record named {started.pid} but nothing was holding the name")
        return started.pid

    @staticmethod
    def what_it_recorded(at: Path) -> Optional[int]:
        """The pid in an agent's record, read without taking a lock. `None` while there is none."""
        how, said = files.read_json(at / standing.RECORD)
        if how != files.READ or not isinstance(said, dict):
            return None
        return programs.a_pid(said.get("pid"))

    def ended(self, started: "subprocess.Popen") -> None:
        """Take away a process this case started, however the case ended.

        The one process this case started, and never its group: a case that signalled a whole group
        would be reaching for processes it did not start. Collected afterwards, because an
        uncollected child answers signal `0` exactly like a running one — and because the object is
        held until then, so a case that stopped the gateway under test leaves nothing behind.
        """
        with contextlib.suppress(OSError):
            started.kill()
        started.wait()

    def a_gateway_nobody_can_ask_about(self) -> None:
        """A lock file that exists and cannot be opened, which is `standing`'s third answer."""
        support.not_as_root(self)
        (self.at / standing.LOCK).write_bytes(b"")
        (self.at / standing.LOCK).chmod(0o000)
        self.addCleanup(lambda: (self.at / standing.LOCK).chmod(0o600))

    def a_placed_job(self, by: Optional[support.ASupervisor] = None) -> support.ASupervisor:
        """A plist really on disk, with no gateway behind it.

        **Placed directly rather than by running a start that fails**, which is how this used to get
        one: a start against a stand-in supervisor placed the job and then could not show a gateway
        holding the name. That stopped leaving a plist the moment a start that cannot prove a
        gateway came up began taking its job back — which it must, because a job whose program
        cannot start is one launchd brings back on the throttle for ever.

        `into` is the scratch root's own `LaunchAgents`, the same answer `support` gives the command,
        so nothing here writes where the owner's machine looks at login.
        """
        by = by or support.ASupervisor()
        one = job.job("cole", directory.where("cole"), paths.home(), paths.home() / "LaunchAgents")
        job.place(one, by)
        return by

    def rundesk_with(self, by: support.ASupervisor, *argv: str) -> Tuple[int, str, str]:
        """Drive the command against this stand-in supervisor rather than the default one."""
        return support.run_with(list(argv), supervising=by)


class Listing(WithAnAgent):
    """`rundesk gateways`, and the four independent places it has to ask."""

    def test_an_install_with_no_agents_says_so_and_says_what_to_type(self):
        self.rundesk("agents", "remove", "cole", "--confirm")
        code, out, _ = self.rundesk("gateways")
        self.assertEqual(OK, code)
        self.assertIn("no agents yet", out)
        self.assertIn("rundesk agents add <agent> --provider <provider>", out)

    def test_where_they_stand_is_said_even_when_there_are_none(self):
        self.rundesk("agents", "remove", "cole", "--confirm")
        _, out, _ = self.rundesk("gateways")
        self.assertIn(str(self.home / "data" / "agents"), out)

    def test_it_reports_all_four_sources_and_not_one_verdict(self):
        # `launchctl print` answering 113 is ambiguous at least four ways and a disabled job prints
        # as a perfectly healthy one, so no single column can carry the answer.
        _, out, _ = self.rundesk("gateways")
        for heading in ("AGENT", "GATEWAY", "JOB", "OVERRIDE", "LOGIN ITEM"):
            self.assertIn(heading, out, f"the {heading} column is not there")

    def test_an_agent_with_no_gateway_and_no_job_says_what_to_type(self):
        code, out, _ = self.rundesk("gateways")
        self.assertEqual(OK, code)
        self.assertIn("not running", out)
        self.assertIn("not placed", out)
        self.assertIn("rundesk gateways start cole", out)

    def test_the_bare_verb_and_the_named_one_answer_the_same(self):
        self.assertEqual(self.rundesk("gateways"), self.rundesk("gateways", "list"))

    def test_every_agent_is_listed(self):
        directory.made("ada", "claude")
        _, out, _ = self.rundesk("gateways")
        self.assertIn("cole", out)
        self.assertIn("ada", out)

    def test_a_running_gateway_is_reported_as_running_with_its_pid(self):
        by = support.ASupervisor(print=ran(0, out="\tstate = running\n"))
        with self.a_running_gateway():
            _, out, _ = self.rundesk_with(by, "gateways")
        self.assertIn("running", out)
        self.assertIn(str(os.getpid()), out)

    def test_a_gateway_with_no_job_behind_it_is_never_called_running(self):
        # It will not come back when it stops and nothing starts it at the next login. Saying
        # "running" tells somebody they are covered at the moment they are least covered.
        with self.a_running_gateway():
            code, out, _ = self.rundesk("gateways")
        self.assertEqual(OK, code)
        self.assertIn("UNSUPERVISED", out)
        self.assertIn("nothing brings it back", out)
        self.assertIn("rundesk gateways restart cole", out)

    def test_a_gateway_that_can_never_be_supervised_is_never_called_running_either(self):
        # This row is reached only when no launchd label can carry the agent's name, so the gateway
        # on it can never have a job in any state — the least supervised a gateway gets. Calling it
        # `running` tells somebody they are covered when nothing will ever bring it back and
        # nothing will ever start it at the next login.
        directory.made(UNLABELABLE, "claude")
        with self.a_running_gateway(UNLABELABLE):
            code, out, _ = self.rundesk("gateways")
        row = next(line for line in out.splitlines() if line.startswith(UNLABELABLE))
        self.assertEqual(OK, code)
        self.assertIn("NEVER SUPERVISED", row)
        self.assertIn("cannot be placed", row)
        self.assertIn(str(os.getpid()), row)

    def test_no_job_ever_is_not_worded_as_no_job_yet(self):
        # Two states, two different things to do about them. `NOT_PLACED` is a job that has not
        # been placed *yet* and a restart places it; this one can never be placed at all, so the
        # same sentence would send somebody round a loop that cannot end.
        directory.made(UNLABELABLE, "claude")
        with self.a_running_gateway(), self.a_running_gateway(UNLABELABLE):
            _, out, _ = self.rundesk("gateways")
        never = next(line for line in out.splitlines() if line.strip().startswith(UNLABELABLE + ":"))
        yet = next(line for line in out.splitlines() if line.strip().startswith("cole:"))
        self.assertIn("rundesk gateways restart cole", yet)
        self.assertIn("can never have a job", never)
        self.assertNotIn("rundesk gateways restart", never)
        self.assertIn(f"rundesk gateways stop '{UNLABELABLE}'", never)

    def test_a_113_with_a_plist_on_disk_is_never_reported_as_not_installed(self):
        # Proven byte-identical for four different situations: a plist never bootstrapped, a label
        # with only a stale override, a label that never existed, and a job launchd threw away.
        self.a_placed_job()
        _, out, _ = self.rundesk("gateways")
        self.assertIn("cannot tell", out)
        self.assertNotIn("not installed", out)
        self.assertIn("log show", out)

    def test_a_disabled_label_says_that_enabling_it_is_the_fix(self):
        # The one lockout that has a resolution — and `print` shows a disabled job as a healthy one,
        # because `disabled` is not among the property words launchd renders at all.
        listed = f'\tdisabled services = {{\n\t\t"{self.label}" => disabled\n\t}}\n'
        by = support.ASupervisor(print=ran(0), **{"print-disabled": ran(0, out=listed)})
        _, out, _ = self.rundesk_with(by, "gateways")
        self.assertIn("disabled", out)
        self.assertIn("enables it", out)
        self.assertIn("rundesk gateways start cole", out)

    def test_an_override_store_that_could_not_be_read_is_not_a_label_that_is_enabled(self):
        by = support.ASupervisor(**{"print-disabled": ran(1, err="nope")})
        _, out, _ = self.rundesk_with(by, "gateways")
        self.assertIn("cannot tell", out)

    def test_a_login_items_denial_names_the_one_thing_the_owner_can_do(self):
        # There is no `launchctl` command and no user-level command of any kind that undoes this.
        self.a_placed_job()
        with mock.patch.object(job, "allowed_by_the_owner", return_value=False):
            _, out, _ = self.rundesk("gateways")
        self.assertIn("switched off", out)
        self.assertIn("System Settings", out)
        self.assertIn("Login Items", out)

    def test_a_background_item_store_that_says_nothing_is_not_an_item_switched_off(self):
        # The format is undocumented, so `job.allowed_by_the_owner` answers `None` for anything it
        # does not recognise. A column that read that as a denial would tell somebody their gateway
        # was switched off on the strength of a bit nobody published.
        _, out, _ = self.rundesk("gateways")
        row = next(line for line in out.splitlines() if line.startswith("cole"))
        self.assertTrue(row.rstrip().endswith("cannot tell"), row)
        self.assertNotIn("switched off", row)

    def test_a_login_items_denial_is_said_even_when_launchd_still_answers_for_the_job(self):
        # The listing's own branch rather than `job.stands`'s: launchd is happy, the job prints as
        # a perfectly healthy one, and the owner has switched it off — so it will not come back at
        # the next login and nothing in launchd's answer says a word about it.
        by = support.ASupervisor(print=ran(0))
        with mock.patch.object(job, "allowed_by_the_owner", return_value=False):
            _, out, _ = self.rundesk_with(by, "gateways")
        self.assertIn("switched off", out)
        self.assertIn("no command of any kind puts it back", out)
        self.assertIn("Login Items", out)

    def test_no_login_session_is_never_reported_as_not_running(self):
        # Over SSH into a machine nobody has logged into at the desktop, every gateway on it would
        # otherwise look absent.
        by = support.ASupervisor(print=ran(job.NO_GUI_SESSION))
        _, out, _ = self.rundesk_with(by, "gateways")
        self.assertIn("login session", out)
        self.assertIn("cannot tell", out)

    def test_a_domain_that_refused_the_verb_is_not_reported_as_no_login_session(self):
        # `112` and `125` shared one name and one sentence, so a `125` told somebody there was no
        # login session and to go and log in at the desktop. The research page measured `125` as
        # "domain does not support specified action", and `allow` already relies on that reading —
        # it retries `enable` in `user/<uid>` when `gui/<uid>` answers `125`. Both are still
        # `cannot tell`; the disposition was never wrong, only the sentence explaining it.
        by = support.ASupervisor(print=ran(job.WRONG_DOMAIN_FOR_THE_VERB))
        _, out, _ = self.rundesk_with(by, "gateways")
        self.assertIn("cannot tell", out)
        self.assertIn("would not answer a question about", out)
        self.assertNotIn("login session", out)

    def test_a_gateway_nobody_can_ask_about_is_not_a_gateway_that_is_not_running(self):
        self.a_gateway_nobody_can_ask_about()
        _, out, _ = self.rundesk("gateways")
        self.assertIn("cannot tell", out)
        self.assertIn("not the same as the gateway not running", out)

    def test_a_listing_that_answered_exits_zero_whatever_it_found(self):
        with self.a_running_gateway():
            code, _, _ = self.rundesk("gateways")
        self.assertEqual(OK, code)


class Starting(WithAnAgent):
    """`rundesk gateways start <agent>` — the resolver, and the gateway it must never kick."""

    def test_it_starts_a_gateway_and_says_where_its_job_and_its_logs_are(self):
        by = ALaunchdThatReallyStarts(self.at)
        self.addCleanup(by.let_go)
        code, out, err = self.rundesk_with(by, "gateways", "start", "cole")
        self.assertEqual(OK, code, err)
        self.assertIn("gateway started for cole", out)
        self.assertIn(self.label, out)
        self.assertIn(str(standing.logs_at(self.at)), out)

    def test_it_enables_then_boots_out_then_bootstraps(self):
        # The override store outlives every plist, launchd holds an imported copy of a plist that
        # nothing watches, and re-bootstrapping a label from another path keeps the definition it
        # already had **without failing**.
        by = ALaunchdThatReallyStarts(self.at)
        self.addCleanup(by.let_go)
        self.rundesk_with(by, "gateways", "start", "cole")
        self.assertEqual(["enable", "bootout", "bootstrap"], by.verbs())

    def test_a_gateway_that_came_up_on_its_own_is_never_kicked(self):
        # `kickstart -k` is kill-then-restart. Bootstrapping is already starting, so an ordinary
        # start has nothing to kick and must not run one.
        by = ALaunchdThatReallyStarts(self.at)
        self.addCleanup(by.let_go)
        self.rundesk_with(by, "gateways", "start", "cole")
        self.assertNotIn("kickstart", by.verbs())

    def test_a_gateway_that_did_not_come_up_is_kicked_past_whatever_it_is_behind(self):
        # The state a kick answers: a crash-looping gateway sitting behind launchd's exponential
        # throttle, where the interval has grown to minutes and the job simply looks dead.
        by = ALaunchdThatReallyStarts(self.at, on=("kickstart",))
        self.addCleanup(by.let_go)
        code, out, err = self.rundesk_with(by, "gateways", "start", "cole")
        self.assertEqual(OK, code, err)
        self.assertIn("kickstart", by.verbs())
        self.assertIn("gateway started for cole", out)

    def test_a_start_on_a_gateway_that_is_already_running_changes_nothing_at_all(self):
        # **The recorded incident, one layer up.** Every step of the resolver begins with a
        # `bootout --wait`, which ends the gateway that is up — so a start that ran it
        # unconditionally would take down an agent in the middle of its work to report it running.
        by = support.ASupervisor(print=ran(0))
        with self.a_running_gateway():
            code, out, _ = self.rundesk_with(by, "gateways", "start", "cole")
        self.assertEqual(OK, code)
        self.assertIn("cole is already running", out)
        self.assertIn("nothing was changed", out)
        self.assertNotIn("bootout", by.verbs())
        self.assertNotIn("kickstart", by.verbs())
        self.assertNotIn("bootstrap", by.verbs())

    def test_a_start_on_a_running_gateway_says_the_pid_that_has_the_name(self):
        by = support.ASupervisor(print=ran(0))
        with self.a_running_gateway():
            _, out, _ = self.rundesk_with(by, "gateways", "start", "cole")
        self.assertIn(str(os.getpid()), out)

    def test_a_running_gateway_with_no_job_is_a_failure_and_names_the_way_out(self):
        # Reporting this as "already running" would tell somebody they were covered when nothing
        # brings that gateway back. The way out is a restart, because a job can only be placed over
        # a name that is free.
        by = support.ASupervisor()
        with self.a_running_gateway():
            code, out, err = self.rundesk_with(by, "gateways", "start", "cole")
        self.assertEqual(FAILED, code)
        self.assertEqual("", out)
        self.assertIn("launchd has no job behind it", err)
        self.assertIn("rundesk gateways restart cole", err)
        self.assertIn("nothing was started", err)
        self.assertNotIn("bootout", by.verbs())

    def test_a_job_launchd_accepted_is_not_reported_as_a_gateway_that_started(self):
        # The whole difference between a plist landing and a process existing. Three plists had sat
        # on the researched machine for two weeks doing nothing at all.
        by = support.ASupervisor()
        code, out, err = self.rundesk_with(by, "gateways", "start", "cole")
        self.assertEqual(FAILED, code)
        self.assertEqual("", out)
        self.assertIn("no gateway came up", err)
        self.assertIn("a job the supervisor accepted is not a gateway that started", err)
        self.assertIn("rundesk gateways logs cole", err)

    def test_a_bootstrap_that_was_refused_is_not_reported_as_a_start(self):
        by = support.ASupervisor(bootstrap=ran(job.IS_DISABLED))
        code, out, err = self.rundesk_with(by, "gateways", "start", "cole")
        self.assertEqual(FAILED, code)
        self.assertEqual("", out)
        self.assertIn("was not placed", err)
        self.assertIn("disabl", err)
        self.assertIn("nothing is running", err)

    def test_a_bootout_that_did_not_clearly_work_stops_the_start(self):
        # Bootstrapping onto a definition launchd may still hold keeps the old one and does not
        # fail, so the whole start would silently go on running the old program.
        by = support.ASupervisor(bootout=ran(5))
        code, _, err = self.rundesk_with(by, "gateways", "start", "cole")
        self.assertEqual(FAILED, code)
        self.assertNotIn("bootstrap", by.verbs())
        self.assertIn("was not placed", err)

    def test_a_supervisor_that_was_never_on_the_machine_is_not_a_refusal(self):
        by = support.ASupervisor(bootstrap=ran(None, trouble=programs.DID_NOT_START))
        code, _, err = self.rundesk_with(by, "gateways", "start", "cole")
        self.assertEqual(FAILED, code)
        self.assertIn(programs.DID_NOT_START, err)

    def test_it_is_safe_to_run_again_on_a_gateway_it_already_started(self):
        by = ALaunchdThatReallyStarts(self.at)
        self.addCleanup(by.let_go)
        self.rundesk_with(by, "gateways", "start", "cole")
        code, out, _ = self.rundesk_with(by, "gateways", "start", "cole")
        self.assertEqual(OK, code)
        self.assertIn("already running", out)

    def test_it_writes_the_plist_and_the_shim_the_job_layer_names(self):
        by = ALaunchdThatReallyStarts(self.at)
        self.addCleanup(by.let_go)
        self.rundesk_with(by, "gateways", "start", "cole")
        self.assertTrue(self.plist().is_file(), f"{self.plist()} is not there")
        self.assertTrue((self.at / "rundesk-gateway-cole").is_file())

    def test_a_gateway_nobody_can_ask_about_is_never_started_over(self):
        # A second gateway started beside a first is the one thing this must never do.
        self.a_gateway_nobody_can_ask_about()
        by = support.ASupervisor()
        code, _, err = self.rundesk_with(by, "gateways", "start", "cole")
        self.assertEqual(FAILED, code)
        self.assertIn("nobody can tell whether a gateway is running", err)
        self.assertEqual([], by.verbs())

    def test_an_agent_that_is_not_there_is_refused(self):
        code, _, err = self.rundesk("gateways", "start", "nobody")
        self.assertEqual(FAILED, code)
        self.assertIn("nobody is not an agent on this install", err)
        self.assertIn("nothing was started", err)

    def test_it_needs_a_name(self):
        code, _, _ = self.rundesk("gateways", "start")
        self.assertEqual(USAGE, code)


class Stopping(WithAnAgent):
    """`rundesk gateways stop <agent> | --all` — one of the two, never both and never neither."""

    def test_a_bare_stop_is_refused_and_shows_both_spellings(self):
        by = support.ASupervisor()
        code, out, err = self.rundesk_with(by, "gateways", "stop")
        self.assertEqual(USAGE, code)
        self.assertEqual("", out)
        self.assertIn("stop was not told which gateway", err)
        self.assertIn("rundesk gateways stop <agent>", err)
        self.assertIn("rundesk gateways stop --all", err)
        self.assertIn("nothing was changed", err)
        self.assertEqual([], by.verbs(), "a bare stop asked the supervisor for something")

    def test_a_name_and_all_together_are_refused(self):
        by = support.ASupervisor()
        code, _, err = self.rundesk_with(by, "gateways", "stop", "cole", "--all")
        self.assertEqual(USAGE, code)
        self.assertIn("two different operations", err)
        self.assertEqual([], by.verbs())

    def test_it_stops_a_running_gateway_and_says_what_it_took(self):
        by = ALaunchdThatReallyStarts(self.at)
        self.addCleanup(by.let_go)
        self.rundesk_with(by, "gateways", "start", "cole")
        code, out, err = self.rundesk_with(by, "gateways", "stop", "cole")
        self.assertEqual(OK, code, err)
        self.assertIn("gateway stopped for cole", out)
        self.assertIn(self.label, out)

    def test_the_plist_goes_with_the_job(self):
        # At login, `loginwindow` bootstraps the LaunchAgents directories on its own — so a stop
        # that left the file behind would be a stop that undid itself the next time somebody
        # logged in, with nothing anywhere having said so.
        by = ALaunchdThatReallyStarts(self.at)
        self.addCleanup(by.let_go)
        self.rundesk_with(by, "gateways", "start", "cole")
        self.assertTrue(self.plist().is_file())
        self.rundesk_with(by, "gateways", "stop", "cole")
        self.assertFalse(self.plist().exists(), "the plist would be bootstrapped again at login")

    def test_a_job_that_could_not_be_taken_back_is_never_reported_as_stopped(self):
        self.a_placed_job()
        by = support.ASupervisor(bootout=ran(5))
        code, out, err = self.rundesk_with(by, "gateways", "stop", "cole")
        self.assertEqual(FAILED, code)
        self.assertEqual("", out)
        self.assertIn("could not be taken back", err)
        self.assertTrue(self.plist().is_file(), "the plist went while the job stayed")

    def test_a_gateway_this_command_would_have_to_kill_itself_to_stop_is_refused(self):
        # A gateway still holding the name after its job came back is stopped by signalling the
        # process — but never when the pid on the record is in this command's own process group.
        # `killpg` there signals this very process and everything beside it, and it is reachable by
        # an honest mistake: a recorded id reused by something started from this shell.
        with self.a_running_gateway():
            code, out, err = self.rundesk("gateways", "stop", "cole")
        self.assertEqual(FAILED, code)
        self.assertEqual("", out)
        self.assertIn("could not be stopped", err)
        self.assertIn("own process group", err)
        self.assertIn("nothing was stopped", err)

    def test_stopping_what_was_never_started_is_the_state_that_was_asked_for(self):
        code, out, _ = self.rundesk("gateways", "stop", "cole")
        self.assertEqual(OK, code)
        self.assertIn("cole is not running", out)

    def test_a_job_with_no_gateway_behind_it_is_taken_back_and_said_so(self):
        self.a_placed_job()
        code, out, _ = self.rundesk("gateways", "stop", "cole")
        self.assertEqual(OK, code)
        self.assertIn("was taken back", out)
        self.assertIn("no gateway was running", out)

    def test_all_stops_every_agent_and_names_each_one(self):
        directory.made("ada", "claude")
        code, out, _ = self.rundesk("gateways", "stop", "--all")
        self.assertEqual(OK, code)
        self.assertIn("cole", out)
        self.assertIn("ada", out)

    def test_all_takes_back_one_full_label_per_agent_and_never_a_family_name(self):
        # A label is a name in the *person's* login domain, and a second install's uninstall once
        # booted out the live install's gateway because both had chosen the same one.
        directory.made("ada", "claude")
        by = support.ASupervisor()
        self.rundesk_with(by, "gateways", "stop", "--all")
        booted = [what for verb, what in by.asked if verb == "bootout"]
        self.assertEqual(sorted([job.label_for("ada", self.home), self.label]), sorted(booted))

    def test_one_agent_failing_does_not_stop_the_others_and_is_still_a_failure(self):
        directory.made("ada", "claude")
        by = support.ASupervisor(bootout=ran(5))
        code, _, err = self.rundesk_with(by, "gateways", "stop", "--all")
        self.assertEqual(FAILED, code)
        self.assertIn("cole", err)
        self.assertIn("ada", err)

    def test_an_agent_that_is_not_there_is_refused(self):
        code, _, err = self.rundesk("gateways", "stop", "nobody")
        self.assertEqual(FAILED, code)
        self.assertIn("nobody is not an agent on this install", err)


class ComingDownGracefully(WithAnAgent):
    """The default for both verbs: `bootout --wait` asks with `SIGTERM` and nothing ever kills."""

    def test_a_stop_asks_and_never_kills(self):
        # `bootout --wait` sends `SIGTERM` and waits for the process to really be gone, up to the
        # job's own `ExitTimeOut`. A gateway is holding somebody's work and gets to finish it.
        by = ALaunchdThatReallyStarts(self.at)
        self.addCleanup(by.let_go)
        self.rundesk_with(by, "gateways", "start", "cole")
        by.asked.clear()
        code, _, err = self.rundesk_with(by, "gateways", "stop", "cole")
        self.assertEqual(OK, code, err)
        self.assertEqual(["bootout", "enable"], by.verbs())

    def test_a_restart_asks_and_never_kills(self):
        by = ALaunchdThatReallyStarts(self.at)
        self.addCleanup(by.let_go)
        self.rundesk_with(by, "gateways", "start", "cole")
        by.asked.clear()
        code, _, err = self.rundesk_with(by, "gateways", "restart", "cole")
        self.assertEqual(OK, code, err)
        self.assertEqual(["bootout", "enable", "enable", "bootout", "bootstrap"], by.verbs())

    def test_nothing_on_the_graceful_path_can_block_for_a_throttle(self):
        # **Measured 2026-08-05**: `kickstart -k` does not get past a `ThrottleInterval`, it waits
        # the whole of one out with the caller blocked — 30 s against a throttle of 30 — while a
        # fresh `bootout --wait` then `bootstrap` puts a new pid up immediately. So an ordinary
        # restart may not reach a kick at all: one that did would take half a minute to do what it
        # does in no time, and it would do it on the path somebody types without a flag.
        by = ALaunchdThatReallyStarts(self.at)
        self.addCleanup(by.let_go)
        self.rundesk_with(by, "gateways", "start", "cole")
        by.asked.clear()
        self.rundesk_with(by, "gateways", "restart", "cole")
        self.assertNotIn("kickstart", by.verbs())

    def test_a_graceful_stop_of_a_gateway_that_is_not_running_still_never_kills(self):
        by = support.ASupervisor()
        self.rundesk_with(by, "gateways", "stop", "cole")
        self.assertNotIn("kill", by.verbs())


class ComingDownByForce(WithAnAgent):
    """`--force`: the kill first, and then everything the ordinary cycle already guaranteed."""

    def test_stop_kills_first_and_then_takes_the_job_back(self):
        # The order is the point and not the set. A `bootout --wait` before the kill would block
        # for the whole `ExitTimeOut` on the one gateway `--force` exists for — the one that is not
        # going to answer `SIGTERM` — and `--force` would buy nothing at all.
        by = ALaunchdThatReallyStarts(self.at)
        self.addCleanup(by.let_go)
        self.rundesk_with(by, "gateways", "start", "cole")
        by.asked.clear()
        code, _, err = self.rundesk_with(by, "gateways", "stop", "cole", "--force")
        self.assertEqual(OK, code, err)
        self.assertEqual(["kill", "bootout", "enable"], by.verbs())

    def test_restart_kills_first_then_boots_out_then_bootstraps(self):
        by = ALaunchdThatReallyStarts(self.at)
        self.addCleanup(by.let_go)
        self.rundesk_with(by, "gateways", "start", "cole")
        by.asked.clear()
        code, _, err = self.rundesk_with(by, "gateways", "restart", "cole", "--force")
        self.assertEqual(OK, code, err)
        verbs = by.verbs()
        self.assertEqual("kill", verbs[0], f"the kill was not first: {verbs}")
        self.assertLess(verbs.index("kill"), verbs.index("bootout"), str(verbs))
        self.assertLess(verbs.index("bootout"), verbs.index("bootstrap"), str(verbs))

    def test_restart_by_force_is_never_a_kickstart(self):
        # It was one, and it failed on a working machine: `kickstart -k` waits out the whole
        # `ThrottleInterval` — 30 s, measured — under a ten-second ceiling.
        by = ALaunchdThatReallyStarts(self.at)
        self.addCleanup(by.let_go)
        self.rundesk_with(by, "gateways", "restart", "cole", "--force")
        self.assertNotIn("kickstart", by.verbs())

    def test_it_says_out_loud_that_the_work_was_taken_away(self):
        by = ALaunchdThatReallyStarts(self.at)
        self.addCleanup(by.let_go)
        self.rundesk_with(by, "gateways", "start", "cole")
        _, out, _ = self.rundesk_with(by, "gateways", "stop", "cole", "--force")
        self.assertIn("mid-flight", out)
        self.assertIn("killed rather than asked", out)

    def test_a_restart_by_force_proves_a_gateway_came_up_rather_than_a_job_accepted(self):
        # What the old `kickstart` never did. `--force` skips the *waiting*, which is what it was
        # asked to skip; it skips none of the proving.
        by = support.ASupervisor()
        code, out, err = self.rundesk_with(by, "gateways", "restart", "cole", "--force")
        self.assertEqual(FAILED, code)
        # The stop half says what it found, exactly as the graceful restart does — `--force` used
        # to say nothing here, which was the one place the two verbs disagreed about a gateway that
        # was not running. What must not appear is a claim that one started.
        self.assertEqual("cole is not running\n", out)
        self.assertIn("no gateway came up", err)

    def test_a_restart_by_force_says_where_the_new_gateway_is(self):
        by = ALaunchdThatReallyStarts(self.at)
        self.addCleanup(by.let_go)
        code, out, err = self.rundesk_with(by, "gateways", "restart", "cole", "--force")
        self.assertEqual(OK, code, err)
        self.assertIn("gateway started for cole", out)
        self.assertIn(self.label, out)

    def test_force_on_a_gateway_that_is_already_stopped_is_not_a_failure(self):
        # launchd answers 113 for a label it has no record of, and `kill` on a job that is not
        # running is `--force` asking for the state the machine is already in.
        by = ALaunchdThatReallyStarts(self.at, **{"kill": ran(job.NOT_KNOWN)})
        self.addCleanup(by.let_go)
        code, out, err = self.rundesk_with(by, "gateways", "restart", "cole", "--force")
        self.assertEqual(OK, code, err)
        self.assertIn("gateway started for cole", out)

    def test_stopping_by_force_what_was_never_started_is_the_state_that_was_asked_for(self):
        code, out, err = self.rundesk("gateways", "stop", "cole", "--force")
        self.assertEqual(OK, code, err)
        self.assertIn("cole is not running", out)
        self.assertNotIn("mid-flight", out, "it claimed to have taken away work nobody was doing")

    def test_stop_by_force_on_an_agent_that_is_not_there_still_refuses(self):
        by = support.ASupervisor()
        code, _, err = self.rundesk_with(by, "gateways", "stop", "nobody", "--force")
        self.assertEqual(FAILED, code)
        self.assertIn("nobody is not an agent on this install", err)
        self.assertEqual([], by.verbs(), "--force reached launchd for an agent that is not there")

    def test_restart_by_force_on_an_agent_that_is_not_there_still_refuses(self):
        by = support.ASupervisor()
        code, _, err = self.rundesk_with(by, "gateways", "restart", "nobody", "--force")
        self.assertEqual(FAILED, code)
        self.assertIn("nobody is not an agent on this install", err)
        self.assertEqual([], by.verbs())

    def test_a_stop_by_force_whose_job_could_not_be_taken_back_is_not_reported_as_stopped(self):
        # The kill is not what makes this a stop. The job coming back is, and a `bootout` that
        # answered anything else may have left it loaded.
        self.a_placed_job()
        by = support.ASupervisor(bootout=ran(5))
        code, out, err = self.rundesk_with(by, "gateways", "stop", "cole", "--force")
        self.assertEqual(FAILED, code)
        self.assertEqual("", out)
        self.assertIn("could not be taken back", err)
        self.assertTrue(self.plist().is_file(), "the plist went while the job stayed")

    def test_the_same_words_describe_force_on_both_verbs(self):
        # Two spellings of one flag is how somebody comes to believe they cost different things.
        _, stopping, _ = self.rundesk("gateways", "stop", "--help")
        _, restarting, _ = self.rundesk("gateways", "restart", "--help")
        for said in ("will not go", "mid-flight"):
            with self.subTest(said=said):
                self.assertIn(said, " ".join(stopping.split()))
                self.assertIn(said, " ".join(restarting.split()))


class WhenThereIsNoJobToTakeBack(WithAnAgent):
    """The absolute: **a gateway must never be stuck, and never locked out.**

    `agents add "my agent"` succeeds, `gateways run "my agent"` is a supported verb, and no launchd
    label can carry that name — so a gateway can be running for an agent that can never have a job.
    Every stopping verb used to refuse the name before it had even asked whether one was running,
    which left the process holding the agent's name with nothing in the product able to take it
    back. These cases are that requirement, and each of them stops a process this case started.
    """

    def setUp(self) -> None:
        super().setUp()
        self.unlabelable = directory.made(UNLABELABLE, "claude")

    def stopped(self, *argv: str) -> Tuple[int, str, str]:
        """Drive one of the stopping verbs against a stand-in supervisor that answers nothing."""
        return self.rundesk_with(support.ASupervisor(), *argv)

    def test_a_gateway_whose_name_can_never_be_a_label_is_stopped_by_pid(self):
        pid = self.a_real_gateway(UNLABELABLE)
        code, out, err = self.stopped("gateways", "stop", UNLABELABLE)
        self.assertEqual(OK, code, err)
        self.assertIn(f"gateway stopped for {UNLABELABLE}", out)
        self.assertFalse(programs.alive(pid), "the process is still running")
        self.assertEqual(standing.OFFLINE, standing.standing(self.unlabelable).how)

    def test_it_says_it_signalled_the_process_and_why_it_had_to(self):
        # Two different things can have happened to a gateway that is now down, and only one of
        # them means launchd will never start it again. A stop that said the same sentence for both
        # would hide the fact that this agent has no job at all.
        self.a_real_gateway(UNLABELABLE)
        _code, out, _err = self.stopped("gateways", "stop", UNLABELABLE)
        self.assertIn("stopped by signalling the process directly", out)
        self.assertIn("cannot be part of a launchd label", out)

    def test_a_gateway_launchd_never_started_is_stopped_by_pid_too(self):
        # The other way in, and the name is perfectly labelable: nothing was ever bootstrapped, so
        # the job comes back cleanly and the name is still held afterwards. That is the proof it
        # was not launchd keeping it up, and a signal is the only thing left that stops it.
        pid = self.a_real_gateway("cole")
        code, out, err = self.stopped("gateways", "stop", "cole")
        self.assertEqual(OK, code, err)
        self.assertIn("gateway stopped for cole", out)
        self.assertIn("stopped by signalling the process directly", out)
        self.assertFalse(programs.alive(pid))

    def test_a_restart_by_force_really_ends_a_gateway_launchd_never_started(self):
        # The one that was reported killed and replaced while it went on running under its original
        # pid. `--force` used to `launchctl kill` the *label*, which reaches a process only while
        # launchd holds a job for it. Against a gateway launchd never started, the kill hit nothing;
        # the replacement launchd bootstrapped found the name already held and stood down as it
        # should; and the check that a gateway was up was then answered by the original process,
        # which had never been touched. Two false claims in one command, about the one state a
        # person runs `--force` to get out of.
        pid = self.a_real_gateway("cole")
        code, out, _err = self.stopped("gateways", "restart", "cole", "--force")
        self.assertFalse(programs.alive(pid),
                         "restart --force left the gateway it said it killed still running")
        self.assertIn("stopped by signalling the process directly", out,
                      "the only thing that can stop a gateway launchd never started")
        self.assertNotIn(f"gateway started for cole as pid {pid}", out,
                         "it reported starting a gateway that is the process it never stopped")
        self.assertNotEqual(OK, code,
                            "the stand-in starts nothing, so a restart that reported success here "
                            "would be claiming a gateway came up that never did")

    def test_the_fallback_is_not_used_when_there_is_a_job(self):
        # An ordinary stop takes the job back and the gateway goes with it. Reaching for a signal
        # there would be this command killing a process launchd was already bringing down
        # gracefully — and killing it under a supervisor that puts it straight back.
        signalled: List[int] = []
        by = ALaunchdThatReallyStarts(self.at)
        self.addCleanup(by.let_go)
        self.rundesk_with(by, "gateways", "start", "cole")
        with mock.patch.object(programs, "stop", lambda pid, *_a, **_kw: signalled.append(pid)):
            code, out, err = self.rundesk_with(by, "gateways", "stop", "cole")
        self.assertEqual(OK, code, err)
        self.assertEqual([], signalled, "a gateway with a job behind it was signalled")
        self.assertNotIn("signalling the process directly", out)

    def test_only_a_pid_the_lock_says_is_running_is_ever_signalled(self):
        # **A pid from a record whose process is gone belongs to something else now.** So the
        # record is read only once the kernel has said somebody is holding the name — here it names
        # a live process that is holding a different agent's name entirely, and signalling it would
        # take away a stranger's program on the strength of a number in a file.
        somebody_else = self.a_real_gateway("cole")
        (self.unlabelable / standing.RECORD).write_text(
            f'{{"name": "{UNLABELABLE}", "pid": {somebody_else}, "version": "0.0.0"}}',
            encoding="utf-8")
        code, out, err = self.stopped("gateways", "stop", UNLABELABLE)
        self.assertEqual(OK, code, err)
        self.assertIn(f"{UNLABELABLE} is not running", out)
        self.assertTrue(programs.alive(somebody_else), "it signalled a pid nothing was holding")

    def test_a_signal_that_was_refused_is_not_a_gateway_that_is_still_running(self):
        # **Measured on this machine, 2026-08-05.** `killpg` against the group of a process that
        # has just become a zombie answers `EPERM` on macOS rather than `ESRCH` — so a gateway that
        # took the `SIGTERM` and died in the instant before the `SIGKILL` behind it has that
        # `SIGKILL` refused, and the program that really did stop is reported as one that would not
        # go. What decides is the lock, exactly as it decides after a `bootout`.
        pid = self.a_real_gateway(UNLABELABLE)
        really = programs.stop

        def stopped_it_and_then_said_otherwise(one: int, *rest: float) -> str:
            really(one, *rest)
            return f"process group {one} could not be signalled ([Errno 1] Operation not permitted)"

        with mock.patch.object(programs, "stop", stopped_it_and_then_said_otherwise):
            code, out, err = self.stopped("gateways", "stop", UNLABELABLE)
        self.assertEqual(OK, code, err)
        self.assertIn(f"gateway stopped for {UNLABELABLE}", out)
        self.assertFalse(programs.alive(pid))

    def test_a_gateway_nobody_can_ask_about_is_never_signalled_on_a_guess(self):
        support.not_as_root(self)
        (self.unlabelable / standing.LOCK).write_bytes(b"")
        (self.unlabelable / standing.LOCK).chmod(0o000)
        self.addCleanup((self.unlabelable / standing.LOCK).chmod, 0o600)
        code, _out, err = self.stopped("gateways", "stop", UNLABELABLE)
        self.assertEqual(FAILED, code)
        self.assertIn("nobody can tell whether a gateway is running", err)
        self.assertIn("nothing was stopped", err)

    def test_stopping_one_that_is_not_running_is_the_state_that_was_asked_for(self):
        code, out, err = self.stopped("gateways", "stop", UNLABELABLE)
        self.assertEqual(OK, code, err)
        self.assertIn(f"{UNLABELABLE} is not running", out)

    def test_force_says_out_loud_that_the_work_was_taken_away(self):
        pid = self.a_real_gateway(UNLABELABLE)
        code, out, err = self.stopped("gateways", "stop", UNLABELABLE, "--force")
        self.assertEqual(OK, code, err)
        self.assertIn("mid-flight", out)
        self.assertFalse(programs.alive(pid))

    def test_force_does_not_wait_where_the_graceful_stop_does(self):
        # **The one gateway `--force` exists for**: one that will not answer `SIGTERM`, so that
        # asking it costs the whole window. Graceful means graceful even here — the window is the
        # same one the job's own `ExitTimeOut` would have given it — and `--force` is the only
        # thing that skips it.
        with mock.patch.object(gateways, "GENTLY_FOR", 1.0):
            asked = self.how_long_a_stop_took()
            forced = self.how_long_a_stop_took("--force")
        self.assertGreaterEqual(asked, 1.0, "the graceful stop did not wait for it to finish")
        self.assertLess(forced, 1.0, "--force waited out a window it was asked to skip")
        self.assertLess(forced, asked)

    def how_long_a_stop_took(self, *argv: str) -> float:
        """Stop a gateway that ignores `SIGTERM`, and hand back how long that took in seconds."""
        pid = self.a_real_gateway(UNLABELABLE, ignoring_sigterm=True)
        started = time.monotonic()
        code, _out, err = self.stopped("gateways", "stop", UNLABELABLE, *argv)
        took = time.monotonic() - started
        self.assertEqual(OK, code, err)
        self.assertFalse(programs.alive(pid), "a gateway ignoring SIGTERM was never insisted on")
        return took

    def test_the_window_it_is_given_is_the_one_its_job_would_have_given_it(self):
        # Asserted rather than assumed, because the case above shortens it: a gateway with no job
        # behind it is holding somebody's work exactly as one with a job is, and a stop that gave
        # it a fraction of a second would take that work away while calling itself graceful.
        self.assertEqual(float(job.EXIT_TIMEOUT), gateways.GENTLY_FOR)

    def test_a_restart_stops_it_and_says_it_can_never_be_started_again(self):
        # Honest in both halves. The gateway really is down — which is the requirement — and the
        # start that cannot follow is said as the failure it is rather than passed over.
        pid = self.a_real_gateway(UNLABELABLE)
        code, out, err = self.stopped("gateways", "restart", UNLABELABLE)
        self.assertEqual(FAILED, code)
        self.assertIn(f"gateway stopped for {UNLABELABLE}", out)
        self.assertFalse(programs.alive(pid))
        self.assertIn("cannot be part of a launchd label", err)
        self.assertIn(f"rundesk gateways run '{UNLABELABLE}'", err)

    def test_a_restart_by_force_stops_it_too(self):
        pid = self.a_real_gateway(UNLABELABLE)
        code, out, err = self.stopped("gateways", "restart", UNLABELABLE, "--force")
        self.assertEqual(FAILED, code)
        self.assertIn(f"gateway stopped for {UNLABELABLE}", out, err)
        self.assertIn("mid-flight", out)
        self.assertFalse(programs.alive(pid))
        self.assertIn("it was stopped and not started again", err)

    def test_what_it_says_to_type_is_what_a_shell_would_accept(self):
        # A name with a space in it is two arguments unless it is quoted, and a command somebody
        # pastes that does something else is worse than one that was never offered.
        _code, _out, err = self.stopped("gateways", "start", UNLABELABLE)
        self.assertIn(f"rundesk gateways run '{UNLABELABLE}'", err)

    def test_all_reaches_the_one_that_has_no_job_as_well(self):
        # The verb somebody types when something is wrong and they do not know which agent it is.
        pid = self.a_real_gateway(UNLABELABLE)
        code, out, err = self.stopped("gateways", "stop", "--all")
        self.assertEqual(OK, code, err)
        self.assertIn(f"gateway stopped for {UNLABELABLE}", out)
        self.assertFalse(programs.alive(pid))


class Restarting(WithAnAgent):
    """`rundesk gateways restart` — and the bare one that took down every gateway somebody had."""

    def test_a_bare_restart_is_refused_and_asks_the_supervisor_for_nothing(self):
        # The recorded incident: the build this replaces let a bare `restart` mean every agent.
        by = support.ASupervisor()
        code, out, err = self.rundesk_with(by, "gateways", "restart")
        self.assertEqual(USAGE, code)
        self.assertEqual("", out)
        self.assertIn("restart was not told which gateway", err)
        self.assertIn("rundesk gateways restart <agent>", err)
        self.assertIn("rundesk gateways restart --all", err)
        self.assertEqual([], by.verbs(), "a bare restart reached for somebody's gateways")

    def test_a_name_and_all_together_are_refused(self):
        by = support.ASupervisor()
        code, _, err = self.rundesk_with(by, "gateways", "restart", "cole", "--all")
        self.assertEqual(USAGE, code)
        self.assertIn("two different operations", err)
        self.assertEqual([], by.verbs())

    def test_it_stops_and_starts_again(self):
        by = ALaunchdThatReallyStarts(self.at)
        self.addCleanup(by.let_go)
        self.rundesk_with(by, "gateways", "start", "cole")
        code, out, err = self.rundesk_with(by, "gateways", "restart", "cole")
        self.assertEqual(OK, code, err)
        self.assertIn("gateway stopped for cole", out)
        self.assertIn("gateway started for cole", out)

    def test_it_never_bootstraps_before_the_old_one_is_proven_gone(self):
        by = ALaunchdThatReallyStarts(self.at)
        self.addCleanup(by.let_go)
        self.rundesk_with(by, "gateways", "start", "cole")
        by.asked.clear()
        self.rundesk_with(by, "gateways", "restart", "cole")
        verbs = by.verbs()
        self.assertLess(verbs.index("bootout"), verbs.index("bootstrap"))

    def test_a_stop_that_did_not_work_reports_a_cycle_that_started_nothing(self):
        self.a_placed_job()
        by = support.ASupervisor(bootout=ran(5))
        code, out, err = self.rundesk_with(by, "gateways", "restart", "cole")
        self.assertEqual(FAILED, code)
        self.assertEqual("", out)
        self.assertIn("could not be taken back", err)
        self.assertIn("was not started again", err)
        self.assertNotIn("bootstrap", by.verbs(), "it started over a job launchd may still hold")

    def test_a_bootstrap_by_force_that_was_refused_is_not_reported_as_a_restart(self):
        # The kill is not what makes this a restart. The bootstrap is.
        by = support.ASupervisor(bootstrap=ran(job.IS_DISABLED))
        code, out, err = self.rundesk_with(by, "gateways", "restart", "cole", "--force")
        self.assertEqual(FAILED, code)
        # The stop half reports what it found, as the graceful restart already did; what must not
        # be there is any claim that a gateway came up.
        self.assertEqual("cole is not running\n", out)
        self.assertIn("was not placed", err)
        self.assertIn("nothing is running", err)

    def test_all_restarts_every_agent(self):
        # Asserted on the labels rather than on the exit code: nothing in this case is going to
        # come up, and what is being proved is that both agents were reached and each by the one
        # full label its own root derives.
        directory.made("ada", "claude")
        by = support.ASupervisor()
        self.rundesk_with(by, "gateways", "restart", "--all")
        booted = {what for verb, what in by.asked if verb == "bootout"}
        self.assertEqual({job.label_for("ada", self.home), self.label}, booted)

    def test_all_by_force_reaches_every_agent_too(self):
        directory.made("ada", "claude")
        by = support.ASupervisor()
        self.rundesk_with(by, "gateways", "restart", "--all", "--force")
        killed = {what for verb, what in by.asked if verb == "kill"}
        self.assertEqual({job.label_for("ada", self.home), self.label}, killed)


class WhatItHasBeenSaying(WithAnAgent):
    """`rundesk gateways logs <agent>` — lines, none yet, or could not be read."""

    def test_it_shows_what_the_gateway_wrote(self):
        logs.note(standing.logs_at(self.at), "gateway up for cole")
        code, out, _ = self.rundesk("gateways", "logs", "cole")
        self.assertEqual(OK, code)
        self.assertIn("gateway up for cole", out)
        self.assertIn(str(standing.logs_at(self.at)), out)

    def test_it_shows_only_as_many_lines_as_were_asked_for(self):
        for at in range(5):
            logs.note(standing.logs_at(self.at), f"line {at}")
        _, out, _ = self.rundesk("gateways", "logs", "cole", "-n", "2")
        self.assertIn("line 4", out)
        self.assertNotIn("line 0", out)

    def test_nothing_written_yet_is_said_as_itself(self):
        code, out, _ = self.rundesk("gateways", "logs", "cole")
        self.assertEqual(OK, code)
        self.assertIn("nothing has been written by cole's own gateway yet", out)

    def test_an_empty_log_shows_what_the_supervisor_caught_instead(self):
        # The only account of a start that died before the gateway had a log of its own — a missing
        # interpreter, a job launchd would not take, an exception on the way up.
        _out, err = standing.captured(self.at)
        err.parent.mkdir(parents=True, exist_ok=True)
        err.write_text("Traceback: no such interpreter\n", encoding="utf-8")
        code, out, _ = self.rundesk("gateways", "logs", "cole")
        self.assertEqual(OK, code)
        self.assertIn("what the supervisor caught", out)
        self.assertIn(str(err), out)
        self.assertIn("no such interpreter", out)

    def test_the_first_line_a_gateway_writes_is_shown_too(self):
        # It goes to standard output, which launchd captures separately, and an empty one beside a
        # job launchd says has run is the signal that the failure is upstream of this product.
        out_file, _err = standing.captured(self.at)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text("[now] gateway cole: this process is pid 42\n", encoding="utf-8")
        _, out, _ = self.rundesk("gateways", "logs", "cole")
        self.assertIn("this process is pid 42", out)

    def test_a_crash_the_supervisor_caught_is_shown_beside_a_day_log_that_has_lines(self):
        # **The incident.** A gateway starts, writes its `up` line, and dies inside its throttle
        # window on an uncaught exception. The next morning the day log holds the `up` line and
        # nothing else, and the traceback is in `gateway.err`. A fallback that fired only on an
        # empty day log was unreachable for ever after the first successful start in the window.
        logs.note(standing.logs_at(self.at), "gateway up for cole")
        _out, err = standing.captured(self.at)
        err.parent.mkdir(parents=True, exist_ok=True)
        err.write_text("Traceback (most recent call last):\nRuntimeError: it fell over\n",
                       encoding="utf-8")
        code, out, _ = self.rundesk("gateways", "logs", "cole")
        self.assertEqual(OK, code)
        self.assertIn("gateway up for cole", out)
        self.assertIn("RuntimeError: it fell over", out)

    def test_each_of_the_two_says_which_file_it_came_from(self):
        # Two orthogonal facts about one gateway, and a person reading them has to know which of
        # the two files they are looking at before they can act on either.
        logs.note(standing.logs_at(self.at), "gateway up for cole")
        _out, err = standing.captured(self.at)
        err.parent.mkdir(parents=True, exist_ok=True)
        err.write_text("RuntimeError: it fell over\n", encoding="utf-8")
        _, out, _ = self.rundesk("gateways", "logs", "cole")
        self.assertIn(f"what cole's own gateway wrote, in {standing.logs_at(self.at)}", out)
        self.assertIn(f"what the supervisor caught in {err}", out)

    def test_a_gateway_with_a_log_of_its_own_is_not_sent_to_the_unified_log(self):
        # `log show` is for a gateway that never started at all. Offering it for one whose own log
        # is right there is sending somebody to look somewhere nothing happened.
        logs.note(standing.logs_at(self.at), "gateway up for cole")
        _, out, _ = self.rundesk("gateways", "logs", "cole")
        self.assertIn("the supervisor caught nothing", out)
        self.assertNotIn("log show", out)

    def test_nothing_anywhere_names_the_one_place_left_to_look(self):
        _, out, _ = self.rundesk("gateways", "logs", "cole")
        self.assertIn("the supervisor caught nothing either", out)
        self.assertIn("log show", out)

    def test_a_log_that_cannot_be_read_is_not_a_gateway_that_said_nothing(self):
        # Handing back an empty list for a directory nobody may read reports a quiet gateway, and
        # whoever reads that goes looking in entirely the wrong place.
        support.not_as_root(self)
        where = standing.logs_at(self.at)
        where.mkdir(parents=True, exist_ok=True)
        where.chmod(0o000)
        self.addCleanup(where.chmod, 0o700)
        code, _, err = self.rundesk("gateways", "logs", "cole")
        self.assertEqual(FAILED, code)
        self.assertIn("could not be read", err)
        self.assertIn("nothing was read", err)

    def test_asking_for_no_lines_at_all_is_refused_rather_than_answered_with_nothing(self):
        # `USAGE`, the same as `-n lots`: one flag answering `2` for a value that is not a number
        # and `1` for a value that is not a count is the same mistake reported two ways.
        code, _, err = self.rundesk("gateways", "logs", "cole", "-n", "0")
        self.assertEqual(USAGE, code)
        self.assertIn("is not a number of lines", err)

    def test_an_agent_that_is_not_there_is_refused(self):
        code, _, err = self.rundesk("gateways", "logs", "nobody")
        self.assertEqual(FAILED, code)
        self.assertIn("nobody is not an agent on this install", err)
        self.assertIn("nothing was read", err)

    def test_a_line_count_that_is_not_a_number_is_a_usage_error(self):
        code, _, _ = self.rundesk("gateways", "logs", "cole", "-n", "lots")
        self.assertEqual(USAGE, code)


class BeingTheGatewayHere(WithAnAgent):
    """`rundesk gateways run <agent>` — the process itself, in this terminal."""

    def test_a_second_gateway_stands_down_rather_than_starting_beside_the_first(self):
        # The claim is the check: there is no version of this that asks first, because between
        # asking and claiming another gateway can arrive.
        with self.a_running_gateway():
            code, out, _ = self.rundesk("gateways", "run", "cole")
        self.assertIn("NOT RUNNING", out)
        self.assertIn("a gateway is already running for cole", out)
        self.assertEqual(OK, code)

    def test_a_refusal_exits_zero_because_that_exit_code_belongs_to_launchd(self):
        # **Deliberate, and the sharpest edge in the product.** Under `KeepAlive {"SuccessfulExit":
        # false}` anything but `0` is a request to be restarted, so a refusal that exited `1` would
        # turn a permanent condition into an endless restart loop that escalates into exponential
        # throttling and simply looks like a hang.
        code, out, _ = self.rundesk("gateways", "run", "nobody")
        self.assertEqual(OK, code)
        self.assertIn("NOT RUNNING", out)
        self.assertIn("there is no agent called nobody", out)

    def test_it_needs_a_name(self):
        code, _, _ = self.rundesk("gateways", "run")
        self.assertEqual(USAGE, code)


class RemovingAnAgentUnderneathItsGateway(WithAnAgent):
    """The seam in `agents remove`, which is the one place this check can be made."""

    def test_an_agent_whose_gateway_is_running_is_not_removed(self):
        with self.a_running_gateway():
            code, out, err = self.rundesk("agents", "remove", "cole", "--confirm")
        self.assertEqual(FAILED, code)
        self.assertEqual("", out)
        self.assertIn("a gateway is running for cole", err)
        self.assertIn("nothing was removed", err)
        self.assertIn("cole", directory.known())

    def test_the_refusal_says_exactly_what_to_type_to_free_it(self):
        with self.a_running_gateway():
            _, _, err = self.rundesk("agents", "remove", "cole", "--confirm")
        self.assertIn("rundesk gateways stop cole", err)

    def test_it_names_the_pid_that_is_holding_the_name(self):
        with self.a_running_gateway():
            _, _, err = self.rundesk("agents", "remove", "cole", "--confirm")
        self.assertIn(str(os.getpid()), err)

    def test_a_gateway_nobody_can_ask_about_is_not_an_agent_that_is_safe_to_remove(self):
        self.a_gateway_nobody_can_ask_about()
        code, _, err = self.rundesk("agents", "remove", "cole", "--confirm")
        self.assertEqual(FAILED, code)
        self.assertIn("nobody can tell whether a gateway is running", err)
        self.assertIn("cole", directory.known())

    def test_an_agent_with_no_gateway_is_removed_as_it_always_was(self):
        code, out, _ = self.rundesk("agents", "remove", "cole", "--confirm")
        self.assertEqual(OK, code)
        self.assertIn("agent cole removed", out)


class UninstallTakesTheJobsBack(WithAnAgent):
    """`uninstall` — the jobs first, because a job that outlives its program starts it at login."""

    def setUp(self) -> None:
        super().setUp()
        support.a_real_tree(self.home / "app")

    def test_it_takes_the_job_back_by_the_full_label_this_root_derives(self):
        # Never a sweep and never a prefix match: `ai.rundesk` is a family, and two installs on one
        # machine derive two different labels for the same agent name.
        by = support.ASupervisor()
        self.rundesk_with(by, "uninstall", "--confirm")
        self.assertEqual([(("bootout"), self.label)],
                         [one for one in by.asked if one[0] == "bootout"])

    def test_it_says_which_job_it_took(self):
        code, out, err = self.rundesk_with(support.ASupervisor(), "uninstall", "--confirm")
        self.assertEqual(OK, code, err)
        self.assertIn(self.label, out)
        self.assertIn("the gateway job for cole", out)

    def test_the_job_comes_back_before_the_program_it_points_at_is_removed(self):
        # A job whose shim hands off to a release that is no longer there is a machine trying to
        # start a command that is gone, at every login, saying so only in the unified log.
        seen = []

        class Watching(support.ASupervisor):
            # `inner` rather than `self`: the case's own `self` is what this closes over,
            # and it is the thing being asserted about.
            def answer(inner, verb, what):
                seen.append((verb, (self.home / "app").exists()))
                return super().answer(verb, what)

        self.rundesk_with(Watching(), "uninstall", "--confirm")
        self.assertIn(("bootout", True), seen, "app/ was already gone when the job was taken back")

    def test_a_job_that_could_not_be_taken_back_stops_the_removal(self):
        by = support.ASupervisor(bootout=ran(5))
        code, out, err = self.rundesk_with(by, "uninstall", "--confirm")
        self.assertEqual(FAILED, code)
        self.assertEqual("", out)
        self.assertIn("could not be taken back", err)
        self.assertTrue((self.home / "app").exists(), "the program went and the job stayed")

    def test_the_plist_and_the_shim_go_with_it(self):
        self.a_placed_job()
        self.assertTrue(self.plist().is_file())
        self.rundesk_with(support.ASupervisor(), "uninstall", "--confirm")
        self.assertFalse(self.plist().exists())

    def test_without_confirming_it_names_the_job_it_would_take(self):
        code, _, err = self.rundesk("uninstall")
        self.assertEqual(FAILED, code)
        self.assertIn(self.label, err)
        self.assertIn("the gateway job for cole", err)

    def test_without_confirming_it_asks_the_supervisor_for_nothing(self):
        by = support.ASupervisor()
        self.rundesk_with(by, "uninstall")
        self.assertEqual([], by.verbs())

    def test_a_purge_takes_the_agents_with_the_data(self):
        code, out, err = self.rundesk_with(support.ASupervisor(), "uninstall", "--confirm",
                                           "--purge")
        self.assertEqual(OK, code, err)
        self.assertIn(self.label, out)
        self.assertFalse((self.home / "data" / "agents" / "cole").exists())

    def test_a_plain_removal_keeps_the_agents_and_still_takes_their_jobs(self):
        _, out, _ = self.rundesk_with(support.ASupervisor(), "uninstall", "--confirm")
        self.assertIn(self.label, out)
        self.assertTrue((self.home / "data" / "agents" / "cole").is_dir())


class OnTheParser(WithAnAgent):
    """The verb as the command line sees it."""

    def test_a_sub_verb_named_wrongly_is_a_usage_error(self):
        code, _, _ = self.rundesk("gateways", "strt", "cole")
        self.assertEqual(USAGE, code)

    def test_a_flag_it_does_not_have_is_a_usage_error(self):
        code, _, _ = self.rundesk("gateways", "start", "cole", "--force")
        self.assertEqual(USAGE, code)

    def test_stop_takes_force_the_same_way_restart_does(self):
        # It had none, which left somebody with a gateway that would not answer `SIGTERM` and no
        # way to stop it — `restart --force` was the only kill in the product, and using it to get
        # a gateway *down* left it up.
        for verb in ("stop", "restart"):
            with self.subTest(verb=verb):
                code, _, _ = self.rundesk("gateways", verb, "cole", "--force")
                self.assertNotEqual(USAGE, code, f"{verb} does not have --force")

    def test_the_verb_is_offered_and_described_where_it_is_listed(self):
        _, out, _ = self.rundesk()
        self.assertIn("gateways", out)

    def test_a_root_that_must_not_be_used_is_refused_rather_than_worked_on(self):
        os.environ["RUNDESK_HOME"] = "/"
        code, out, err = self.rundesk("gateways")
        self.assertEqual(FAILED, code)
        self.assertEqual("", out)
        self.assertIn("root of the filesystem", err)


class TheExitCodes(WithAnAgent):
    """Every code this group hands back, against `docs/commands.md`'s table of three.

    `0` it was done, `1` it was attempted and did not work, `2` **the command line itself was
    wrong**. A person reads the words and a script reads the number, and a script that reads the
    wrong number carries on as though the work happened — which is what two guards here caused by
    refusing a command line that named neither a gateway nor `--all` with a `1`.
    """

    def test_a_command_line_that_was_itself_wrong_is_always_two(self):
        for argv in (("gateways", "stop"),
                     ("gateways", "stop", "cole", "--all"),
                     ("gateways", "restart"),
                     ("gateways", "restart", "cole", "--all"),
                     ("gateways", "strt", "cole"),
                     ("gateways", "start"),
                     ("gateways", "start", "cole", "--all"),
                     ("gateways", "run"),
                     ("gateways", "logs"),
                     ("gateways", "logs", "cole", "-n", "lots"),
                     ("gateways", "logs", "cole", "-n", "0")):
            with self.subTest(argv=argv):
                code, _, _ = self.rundesk(*argv)
                self.assertEqual(USAGE, code)

    def test_a_command_line_that_was_right_and_could_not_be_carried_out_is_always_one(self):
        for argv in (("gateways", "start", "nobody"),
                     ("gateways", "stop", "nobody"),
                     ("gateways", "stop", "nobody", "--force"),
                     ("gateways", "restart", "nobody"),
                     ("gateways", "restart", "nobody", "--force"),
                     ("gateways", "logs", "nobody")):
            with self.subTest(argv=argv):
                code, _, _ = self.rundesk(*argv)
                self.assertEqual(FAILED, code)

    def test_a_question_that_was_answered_is_always_zero(self):
        # Including the states that are bad news. The code says whether the question was answered,
        # and `rundesk gateways && …` asks whether the listing worked.
        for argv in (("gateways",),
                     ("gateways", "list"),
                     ("gateways", "logs", "cole"),
                     ("gateways", "stop", "cole"),
                     ("gateways", "stop", "cole", "--force"),
                     ("gateways", "stop", "--all"),
                     ("gateways", "run", "nobody")):
            with self.subTest(argv=argv):
                code, _, err = self.rundesk(*argv)
                self.assertEqual(OK, code, err)


class TheSeamItself(WithAnAgent):
    """That the supervisor is passed in, and that nothing here can reach the real one."""

    def test_nothing_binds_a_supervisor_in_a_signature(self):
        # A default bound in a signature is decided once, when the module is defined, and nothing
        # can reach past it — which for this seam means a suite against the owner's real jobs.
        import inspect

        from rundesk import cli
        from rundesk.commands import uninstall
        for named in (cli.main, gateways.cmd_gateways, uninstall.cmd_uninstall):
            with self.subTest(function=named.__name__):
                self.assertIsNone(inspect.signature(named).parameters["supervising"].default)

    def test_a_case_that_says_nothing_still_never_reaches_the_real_supervisor(self):
        # `run_with` replaces `job.Launchd` with something that raises for the length of every
        # command it drives, so a default that was not passed would end this case rather than
        # answering — against the owner's own login session.
        code, _, _ = self.rundesk("gateways")
        self.assertEqual(OK, code)

    def test_the_guard_that_would_have_caught_it_really_raises(self):
        with self.assertRaises(AssertionError):
            support.NeverTheRealOne()

    def test_a_stand_in_inherits_nothing_from_the_real_supervisor(self):
        # A `Protocol` rather than a base class, so a stand-in has nothing in common with the real
        # one but the shape — and nothing in `job` can reach a method the seam does not name.
        self.assertEqual((object,), support.ASupervisor.__bases__)

    def test_the_waits_the_product_ships_are_long_enough_to_be_waits(self):
        # Every case here shortens them, so what ships is asserted rather than assumed: a start
        # that gave a real gateway a hundredth of a second to come up would report every ordinary
        # start as a failure, and no case in this file would have noticed.
        for named, seconds in self.as_shipped.items():
            with self.subTest(named=named):
                self.assertGreaterEqual(seconds, 1.0, f"{named} is not a wait, it is a glance")


class TheOwnersLoginItems(unittest.TestCase):
    """Proof, in the middle of the run as well as after every case."""

    def test_this_run_wrote_no_rundesk_plist_into_them(self):
        # The whole reason the plist directory is redirected for every command a case drives.
        #
        # **Measured against what was there when the run began, not against nothing.** Asserting no
        # rundesk plist existed at all made the suite unrunnable for anybody who had used
        # `./dev gateways start` — which places a real job in the owner's login domain on purpose,
        # because a launchd label belongs to the person and no root can move it. That turned "the
        # suite writes nothing here" into "you may not run the product you are testing".
        # **By name, not by (name, size, mtime).** A gateway somebody started by hand before the run
        # goes on being supervised while the suite runs: launchd respawns it, a `restart` rewrites
        # its plist, and its mtime moves. None of that is this run placing a job, and comparing the
        # whole tuple reported all of it as one.
        began = {one[0] for one in (support.AS_THE_RUN_BEGAN or [])}
        written = [one for one in (support.login_items_as_they_stand() or [])
                   if job.FAMILY in one[0] and one[0] not in began]
        self.assertEqual([], written, f"a rundesk plist was written into {support.THEIR_LOGIN_ITEMS}")

    def test_the_guard_that_watches_them_really_fails_when_they_differ(self):
        # A check that cannot fail is a check nobody should trust — and this one cannot be proved
        # the honest way, by changing the thing it watches. So it is handed a reading that is not
        # what is there, which is the same comparison from the other side.
        watched: List[Tuple[str, int, int]] = [("nothing-of-the-sort.plist", 1, 2)]
        with self.assertRaises(AssertionError) as refused:
            support.Isolated.assert_their_login_items_are_untouched(self, watched)
        self.assertIn(str(support.THEIR_LOGIN_ITEMS), str(refused.exception))

    def test_the_guard_passes_the_directory_as_it_really_stands(self):
        support.Isolated.assert_their_login_items_are_untouched(
            self, support.login_items_as_they_stand())


if __name__ == "__main__":
    unittest.main()
