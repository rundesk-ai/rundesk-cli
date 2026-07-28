"""Handing a gateway to the machine, so that nobody has to keep it running.

rundesk supervises nothing. What keeps a gateway up, brings it back when it falls over
and starts it again after a restart is the thing the machine already ships — this module
only writes down what to run and asks that thing to take it (R-GW-1, R-GW-2, R-GW-3).

One job per gateway, named for it, so that cycling one leaves the others alone. That is
the same reason a gateway is one per name, and the two have to agree: a single shared job
would make starting the second agent evict the first.

**Exit codes are the whole of the conversation.** The supervisor is told to bring a
gateway back only when it ends badly, so a gateway that is *refusing* to run — its
virtualenv does not fit, or another already holds its name — must end **well**. Ending
badly would have it started again ten seconds later, forever, which is the failure the
refusal existed to prevent (R-GW-25).

Every call out to the machine is an argument rather than an import, so all of this is
exercised without a supervisor anywhere near it.
"""

from __future__ import annotations

import contextlib
import os
import plistlib
import time
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from rundesk import ROOT, backups_home, data_home, gateway

#: Every job rundesk writes is named this way, so what belongs to rundesk is obvious in
#: a directory full of other people's jobs, and one gateway's job never collides with
#: another's.
PREFIX = "ai.rundesk"

#: How long to wait for the machine to catch up with what it just said it did. Taking a
#: job away is not finished when the command returns, and bootstrapping while the old one
#: is still going away fails with an error that reads like nothing to do with timing.
SETTLE_SECONDS = 10.0

#: How long to wait on the machine to answer. A wedged supervisor would otherwise hang
#: `stop` or `restart` with nothing watching *this* process to recover it — and nothing
#: rundesk does may wait without a bound.
ANSWER_TIMEOUT_SECONDS = 30.0

#: How long the machine waits before starting a gateway again. Stops a gateway that
#: cannot start from being started as fast as the machine can manage.
THROTTLE_SECONDS = 10

#: Where the machine keeps jobs a person owns, rather than jobs the whole machine runs.
LAUNCH_AGENTS = "~/Library/LaunchAgents"


def jobs_home() -> str:
    """Where this machine keeps a person's jobs. Said, so removal can be exercised
    without writing into the real one."""
    return os.environ.get("RUNDESK_JOBS_DIR") or LAUNCH_AGENTS

#: What a gateway is given to find things with. The machine hands a job almost nothing,
#: so a program that a gateway will later run has to be findable from here.
PATH = "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"

#: And where a person's own tools go, which is not one of those. **This was missing and it
#: cost a brain.** A fresh machine reports `the Codex CLI is not on this machine's path`
#: while `which codex` in the owner's shell answers perfectly well — because the shell has
#: `~/.local/bin` and a supervised gateway did not.
#:
#: It is rundesk's own default, which is what makes leaving it out indefensible rather than
#: merely unlucky: `install.sh` puts the `rundesk` command here whenever `/usr/local/bin` is
#: not writable, which on a machine without Homebrew is always. So rundesk installed itself
#: into a directory it then refused to look in.
WHERE_A_PERSONS_OWN_TOOLS_GO = ".local/bin"


def path_for_a_job() -> str:
    """The PATH a job carries, resolved rather than fixed at import.

    `~/.local/bin` is one person's, so it cannot be a constant string in a module that is
    imported once — a suite that redirects `HOME` would still be writing the developer's own
    directory into every job it wrote.
    """
    return f"{PATH}:{Path.home() / WHERE_A_PERSONS_OWN_TOOLS_GO}"


class NoSupervisor(Exception):
    """This machine has nothing of the kind rundesk knows how to hand a gateway to."""


class NotOurs(Exception):
    """A job named like one of ours, which this install did not write."""


class Unsure(Exception):
    """The machine did not answer, so what it holds is unknown rather than absent."""


@dataclass
class Spoke:
    """What the machine said when it was asked to do something."""

    ok: bool
    said: str
    #: Whether the machine answered at all. Not answering is *not* the same as answering
    #: no, and code that cannot tell them apart reads silence from a busy machine as
    #: "there is no such job" — which is how a timeout came to delete the only
    #: description a second attempt would have needed.
    answered: bool = True


def label(name: str) -> str:
    """What the machine calls this gateway's job.

    Checked here as well as where a gateway is made: `start` and `stop` reach the machine
    without ever constructing one, so a name that escapes its directory would otherwise
    plant a job wherever it liked and have the machine keep it running.
    """
    return f"{PREFIX}.{gateway.checked(name)}"


def job_path(name: str, where: str | None = None) -> Path:
    return Path(os.path.expanduser(where or jobs_home())) / f"{label(name)}.plist"


def available() -> bool:
    """Does this machine have the supervisor rundesk knows how to use?"""
    return shutil.which("launchctl") is not None


def ask(*args: str) -> Spoke:
    """Ask the machine to do something, and say what it said."""
    if not available():
        raise NoSupervisor(
            "this machine has no launchd, so rundesk cannot hand it a gateway to keep up"
        )
    try:
        done = subprocess.run(
            ["launchctl", *args], capture_output=True, text=True,
            timeout=ANSWER_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return Spoke(
            False, f"the machine did not answer within {ANSWER_TIMEOUT_SECONDS:g}s", answered=False
        )
    return Spoke(done.returncode == 0, (done.stdout + done.stderr).strip())


def _environment(logs: Path, run: Path | None = None, agents: Path | None = None) -> dict:
    """Where things are, written into a job rather than left to whatever starts it.

    **The machine hands a job almost nothing**, so a place rundesk can be pointed at that the
    job does not name is a place the started process resolves differently from the command
    that wrote the job — and they then disagree about whether anything is running at all,
    which is the one thing neither may be wrong about. That is why this dictionary exists.

    Every job rundesk writes carries the same set, which is why it is built here and not in
    each of them: the two that exist were already identical key for key, and `RUNDESK_BACKUP_DIR`
    had to be added to both in one commit — the second copy is exactly the thing that is not
    added next time.

    The roots are carried as well as the directories that default from them. An install
    pointed elsewhere keeps its data there, so a job carrying only one of the two leaves the
    other's fallback wrong.
    """
    return {
        "PATH": path_for_a_job(),
        "HOME": str(Path.home()),
        "RUNDESK_RUN_DIR": str(run or gateway.home()),
        "RUNDESK_LOG_DIR": str(logs),
        "RUNDESK_JOBS_DIR": os.path.expanduser(jobs_home()),
        "RUNDESK_DATA_DIR": str(data_home()),
        "RUNDESK_INSTALL_DIR": os.environ.get("RUNDESK_INSTALL_DIR", str(ROOT.parent)),
        # An agent keeps everything of its own in one directory, and which directory that is
        # has to reach the gateway the machine starts. Passed rather than resolved here,
        # because a gateway knows nothing of agents and this module knows only what it is
        # handed (R-AGT-9).
        "RUNDESK_AGENTS_DIR": str(agents) if agents else os.environ.get(
            "RUNDESK_AGENTS_DIR", str(data_home() / "agents")),
        # The one directory an owner may point off the machine entirely. A job that did not
        # name it would have the daily backup writing under the install while every copy the
        # owner has ever seen sits on their external disk — two sets, and the one they would
        # look for after trouble is the one that stopped being written to.
        "RUNDESK_BACKUP_DIR": str(backups_home()),
    }


def describe(name: str, root: Path | None = None, logs: Path | None = None,
             run: Path | None = None, agents: Path | None = None) -> dict:
    """The job: what to run, and what the machine should do about it.

    `KeepAlive` is conditional rather than plain: a gateway that ended well was either
    asked to stop or is refusing to run, and neither is a thing to undo (R-GW-25).
    """
    root = root or ROOT
    logs = logs or gateway.logs_home()
    return {
        "Label": label(name),
        # The installed command, by where it actually is. The machine hands a job no
        # PATH worth the name, so a command named rather than located is not found.
        "ProgramArguments": [str(root / "rundesk"), "serve", name],
        "WorkingDirectory": str(root),
        # Where things are, written into the job rather than left to whatever environment
        # the gateway is started with. The machine hands a job almost nothing, so without
        # this a supervised gateway uses the default places while the command that started
        # it reads wherever it was pointed — and they then disagree about whether anything
        # is running at all, which is the one thing neither may be wrong about.
        #
        # There was a fifth, for where schedules were kept, and leaving it out had silently
        # split the machine in two: a schedule could be added, listed and shown as due by
        # the command line while the gateway keeping the machine knew nothing of it. It is
        # gone because a schedule is a row an agent keeps, so where agents are is the whole
        # of what has to agree.
        "EnvironmentVariables": _environment(logs, run, agents),
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": THROTTLE_SECONDS,
        "StandardOutPath": str(logs / f"{name}.out"),
        "StandardErrorPath": str(logs / f"{name}.err"),
    }


# ------------------------------------------------------------------- the install's own job
#
# Everything above is one gateway's. This is the other kind: a job that belongs to the install
# rather than to any agent, runs at a stated hour rather than staying up, and ends.
#
# **The label is deliberately not under `PREFIX.`** — `described()` finds gateways by globbing
# `ai.rundesk.*.plist`, so a job called `ai.rundesk.backup` would be reported as a gateway
# called `backup`: `_every_name` would offer it to `_stand_all_down`, an uninstall would try to
# stop it as though it were one, and an agent an owner really did call `backup` would collide
# with it outright. `ai.rundesk-backup` cannot be matched by that glob, because the glob wants a
# literal dot where this has a hyphen. Structurally unable to collide, rather than remembered.

#: The install's own job, in a namespace beside the gateways rather than inside it.
BACKUP_LABEL = f"{PREFIX}-backup"
UPDATE_LABEL = f"{PREFIX}-update"
AUTOMATIC_UPDATE_LABEL = f"{PREFIX}-automatic-update"
AUTOMATIC_UPDATE_LOGS_MARKER = ".automatic-update-owned"


def backup_job_path(where: str | None = None) -> Path:
    return Path(os.path.expanduser(where or jobs_home())) / f"{BACKUP_LABEL}.plist"


def describe_backup(at: str, root: Path | None = None, logs: Path | None = None) -> dict:
    """The daily backup job: what to run, and when the machine should run it.

    **No `KeepAlive`.** Every job above this one is a thing that must stay up, and the key
    that keeps it up would, on a job that finishes in a second, start it again immediately
    and for ever. What is wanted here is the opposite: run, end, and do not be revived until
    the hour comes round again.

    **`StartCalendarInterval`, not an interval.** An owner states a time of day. A period
    would drift against the clock and would fire at a different hour after every restart.
    """
    root = root or ROOT
    logs = logs or gateway.logs_home()
    hour, _, minute = at.partition(":")
    return {
        "Label": BACKUP_LABEL,
        "ProgramArguments": [str(root / "rundesk"), "backups", "add"],
        "WorkingDirectory": str(root),
        # The same places every job carries, from the one place that decides them.
        "EnvironmentVariables": _environment(logs),
        "StartCalendarInterval": {"Hour": int(hour), "Minute": int(minute)},
        "RunAtLoad": False,
        "StandardOutPath": str(logs / "backups.out"),
        "StandardErrorPath": str(logs / "backups.err"),
    }


def write_backup(at: str, root: Path | None = None, logs: Path | None = None,
                 where: str | None = None) -> Path:
    """Put the install's own job where the machine looks for it."""
    path = backup_job_path(where)
    path.parent.mkdir(parents=True, exist_ok=True)
    (logs or gateway.logs_home()).mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as file:
        plistlib.dump(describe_backup(at, root, logs), file)
    return path


def install_backup(at: str, root: Path | None = None, logs: Path | None = None,
                   where: str | None = None, asking: Callable[..., Spoke] = ask) -> Spoke:
    """Hand the daily backup to the machine, replacing any job of ours already there."""
    asking("bootout", f"{domain()}/{BACKUP_LABEL}")
    path = write_backup(at, root, logs, where)
    return asking("bootstrap", domain(), str(path))


def remove_backup(where: str | None = None, asking: Callable[..., Spoke] = ask) -> Spoke:
    """Ask the machine to let the daily backup go, and take its description away.

    Unlike a gateway's, the description *is* removed here: nothing else names this job, there
    is no process of its own that could outlive it, and a description left behind is a job the
    machine picks up again at the next login after an owner asked for it to stop.
    """
    said = asking("bootout", f"{domain()}/{BACKUP_LABEL}")
    with contextlib.suppress(OSError):
        os.remove(backup_job_path(where))
    return said


def keeps_backups(where: str | None = None) -> bool:
    """Whether this install has given the machine a daily backup to run."""
    return backup_job_path(where).is_file()


def update_job_path(where: str | None = None) -> Path:
    return Path(os.path.expanduser(where or jobs_home())) / f"{UPDATE_LABEL}.plist"


def automatic_update_job_path(where: str | None = None) -> Path:
    return Path(os.path.expanduser(where or jobs_home())) / f"{AUTOMATIC_UPDATE_LABEL}.plist"


def _prepare_automatic_update_logs(logs: Path | None = None) -> Path:
    """Make the job's log directory and remember when Rundesk owns an empty default one."""
    logs = logs or gateway.logs_home()
    logs.mkdir(parents=True, exist_ok=True)
    marker = logs / AUTOMATIC_UPDATE_LOGS_MARKER
    # A configured log directory belongs to its owner even while empty. The default is
    # Rundesk's to remove only while it still contains nothing an owner could need.
    if logs == data_home() / "logs" and not any(logs.iterdir()):
        marker.write_text("created for automatic update logs\n", encoding="utf-8")
    return logs


def _release_automatic_update_logs(logs: Path | None = None) -> None:
    logs = logs or gateway.logs_home()
    marker = logs / AUTOMATIC_UPDATE_LOGS_MARKER
    if not marker.is_file():
        return
    marker.unlink()
    with contextlib.suppress(OSError):
        logs.rmdir()


def describe_automatic_update(at: str, root: Path | None = None,
                              logs: Path | None = None) -> dict:
    """The daily trigger. It only queues the crash-recoverable worker and then ends
    (R-UPD-42)."""
    root = root or ROOT
    logs = logs or gateway.logs_home()
    hour, _, minute = at.partition(":")
    return {
        "Label": AUTOMATIC_UPDATE_LABEL,
        "ProgramArguments": [str(root / "rundesk"), "update", "--automatic"],
        "WorkingDirectory": str(root),
        "EnvironmentVariables": _environment(logs),
        "StartCalendarInterval": {"Hour": int(hour), "Minute": int(minute)},
        "RunAtLoad": False,
        "StandardOutPath": str(logs / "automatic-update.out"),
        "StandardErrorPath": str(logs / "automatic-update.err"),
    }


def write_automatic_update(at: str, root: Path | None = None, logs: Path | None = None,
                           where: str | None = None) -> Path:
    path = automatic_update_job_path(where)
    path.parent.mkdir(parents=True, exist_ok=True)
    _prepare_automatic_update_logs(logs)
    with open(path, "wb") as file:
        plistlib.dump(describe_automatic_update(at, root, logs), file)
    return path


def install_automatic_update(at: str, root: Path | None = None, logs: Path | None = None,
                             where: str | None = None,
                             asking: Callable[..., Spoke] = ask) -> Spoke:
    """Hand the configured daily trigger to the machine without running an update now."""
    root = root or ROOT
    _prepare_automatic_update_logs(logs)
    path = automatic_update_job_path(where)
    if path.exists():
        if not ours(path, root):
            raise NotOurs("the automatic update job was not written by this install of rundesk")
        loaded = asking("print", f"{domain()}/{AUTOMATIC_UPDATE_LABEL}")
        if not loaded.answered:
            return loaded
        try:
            with open(path, "rb") as file:
                current = plistlib.load(file)
        except (OSError, ValueError):
            current = None
        if loaded.ok and current == describe_automatic_update(at, root, logs):
            return Spoke(True, "")
        if loaded.ok:
            stopped = asking("bootout", f"{domain()}/{AUTOMATIC_UPDATE_LABEL}")
            if not stopped.ok:
                return stopped
    path = write_automatic_update(at, root, logs, where)
    return asking("bootstrap", domain(), str(path))


def remove_automatic_update(where: str | None = None, root: Path | None = None,
                            asking: Callable[..., Spoke] = ask,
                            logs: Path | None = None) -> Spoke:
    path = automatic_update_job_path(where)
    if not path.exists():
        _release_automatic_update_logs(logs)
        return Spoke(True, "")
    if not ours(path, root):
        raise NotOurs("the automatic update job was not written by this install of rundesk")
    said = asking("bootout", f"{domain()}/{AUTOMATIC_UPDATE_LABEL}")
    with contextlib.suppress(OSError):
        os.remove(path)
    _release_automatic_update_logs(logs)
    return said


def describe_update_worker(root: Path | None = None, logs: Path | None = None) -> dict:
    """A one-shot worker owned beside gateways, never by one it may stop."""
    root = root or ROOT
    logs = logs or gateway.logs_home()
    environment = _environment(logs)
    if os.environ.get("RUNDESK_UPDATE_ROOT"):
        environment["RUNDESK_UPDATE_ROOT"] = os.environ["RUNDESK_UPDATE_ROOT"]
    return {
        "Label": UPDATE_LABEL,
        "ProgramArguments": [str(root / "rundesk"), "update", "--worker"],
        "WorkingDirectory": str(root),
        "EnvironmentVariables": environment,
        # Reconcile a pending/running request after login; a final request exits at once.
        "RunAtLoad": True,
        # A crash is retried. A reported failure exits non-zero once, then the retry sees
        # its durable final state and exits successfully rather than looping.
        "KeepAlive": {"SuccessfulExit": False},
        "StandardOutPath": str(logs / "update-worker.out"),
        "StandardErrorPath": str(logs / "update-worker.err"),
    }


def write_update_worker(root: Path | None = None, logs: Path | None = None,
                        where: str | None = None) -> Path:
    path = update_job_path(where)
    path.parent.mkdir(parents=True, exist_ok=True)
    (logs or gateway.logs_home()).mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as file:
        plistlib.dump(describe_update_worker(root, logs), file)
    return path


def install_update_worker(root: Path | None = None, logs: Path | None = None,
                          where: str | None = None,
                          asking: Callable[..., Spoke] = ask) -> Spoke:
    """Load and start the external update worker."""
    asking("bootout", f"{domain()}/{UPDATE_LABEL}")
    path = write_update_worker(root, logs, where)
    said = asking("bootstrap", domain(), str(path))
    if said.ok:
        kicked = asking("kickstart", f"{domain()}/{UPDATE_LABEL}")
        return kicked if not kicked.ok else said
    return said


def update_worker_loaded(asking: Callable[..., Spoke] = ask) -> bool:
    """Whether the machine still owns the one-shot update worker.

    The durable request and the supervisor job are two halves of one update. A request may
    still say ``running`` after an unrelated process has booted its worker out, so recovery
    must ask launchd rather than infer ownership from the request or its plist (R-UPD-36,
    R-UPD-37).
    """
    said = asking("print", f"{domain()}/{UPDATE_LABEL}")
    if not said.answered:
        raise Unsure("the machine did not say whether it holds the update worker")
    return said.ok


def kick_update_worker(asking: Callable[..., Spoke] = ask) -> Spoke:
    """Make a loaded one-shot worker run, without replacing a worker already running."""
    return asking("kickstart", f"{domain()}/{UPDATE_LABEL}")


def remove_update_worker(where: str | None = None, root: Path | None = None,
                         asking: Callable[..., Spoke] = ask) -> Spoke:
    """Remove only the update worker description written by this install.

    The label is per user, not per scratch directory. Booting it out merely because an
    isolated uninstall found launchd once terminated the live install's waiting worker and
    left its durable request ``running`` forever. The plist is the ownership evidence, the
    same way it is for a gateway: absent means there is nothing of this install to remove;
    foreign means refuse before asking the machine (R-UPD-35, R-RM-9).
    """
    path = update_job_path(where)
    if not path.exists():
        return Spoke(True, "")
    if not ours(path, root):
        raise NotOurs("the update worker was not written by this install of rundesk")
    said = asking("bootout", f"{domain()}/{UPDATE_LABEL}")
    with contextlib.suppress(OSError):
        os.remove(path)
    return said


def write(name: str, root: Path | None = None, logs: Path | None = None,
          where: str | None = None, run: Path | None = None,
          agents: Path | None = None) -> Path:
    """Put the job where the machine looks for it."""
    path = job_path(name, where)
    path.parent.mkdir(parents=True, exist_ok=True)
    (logs or gateway.logs_home()).mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as file:
        plistlib.dump(describe(name, root, logs, run, agents), file)
    return path


def domain() -> str:
    return f"gui/{os.getuid()}"


def loaded(name: str, asking: Callable[..., Spoke] = ask) -> bool:
    """Does the machine actually have this job right now?

    Asked of the machine rather than inferred from a file. A job description sitting in
    the directory is not a job the machine is keeping — the two come apart whenever a
    job is taken away without the file going with it, and reporting the file as though
    it were the job tells an owner their gateway is looked after when nothing is.
    """
    said = asking("print", f"{domain()}/{label(name)}")
    if not said.answered:
        # Silence is not "there is no such job". Read that way, a busy machine turns a
        # supervised gateway into one that looks hand-started — and whatever is deciding
        # on that basis decides wrongly. Raised, so nothing quietly guesses.
        raise Unsure(f"the machine did not say whether it holds the job for '{name}'")
    return said.ok


def _still_holds(name: str, asking: Callable[..., Spoke]) -> bool:
    """Does the machine still hold this job? Silence counts as *yes*.

    The safe way round: acting on "it is gone" while the machine has not said so is what
    deletes a description of a job that is still running. Waiting longer than necessary
    costs a few seconds.
    """
    try:
        return loaded(name, asking)
    except Unsure:
        return True


def _gone_from(name: str, asking: Callable[..., Spoke], patience: float | None = None) -> bool:
    """Wait for the machine to finish taking a job away, and say whether it did.

    The patience resolves here, not in the signature: a default argument is bound once,
    when this file is read, so naming the constant there freezes it — and anything that
    changed it afterwards, a test included, was quietly ignored and spent the real wait.
    """
    deadline = time.monotonic() + (SETTLE_SECONDS if patience is None else patience)
    while time.monotonic() < deadline:
        if not _still_holds(name, asking):
            return True
        time.sleep(0.2)
    return not _still_holds(name, asking)


def install(
    name: str,
    root: Path | None = None,
    logs: Path | None = None,
    where: str | None = None,
    asking: Callable[..., Spoke] = ask,
    run: Path | None = None,
    agents: Path | None = None,
) -> Spoke:
    """Write this gateway's job and hand it to the machine (R-GW-1, R-GW-2, R-GW-3).

    Any older job of the same name goes first: two jobs for one gateway would have the
    machine starting a second that immediately refuses, over and over. Older *of ours*,
    though — a job of this name that something else wrote is not ours to evict.

    And it must be *gone* before the new one is offered. Taking a job away returns before
    the machine has finished doing it, and offering a replacement into that gap fails
    with an input/output error that says nothing about timing — leaving no job at all,
    so the next attempt succeeds and the one after that fails, alternately, forever.
    """
    _only_ours(name, where, root)
    asking("bootout", f"{domain()}/{label(name)}")
    if not _gone_from(name, asking):
        return Spoke(False, "the old job is still going away, so a new one was not offered")
    path = write(name, root, logs, where, run, agents)
    return asking("bootstrap", domain(), str(path))


def remove(name: str, where: str | None = None, root: Path | None = None,
           asking: Callable[..., Spoke] = ask) -> Spoke:
    """Ask the machine to let go of this gateway's job.

    The description is left exactly where it is. It is the only thing that names this
    job — `described` finds a gateway by globbing for it and by nothing else — so
    whether it can be forgotten is not a question this can answer: the machine letting
    go is only half of it, and the gateway itself may still be running. `take_all_back`
    decides, once it has watched both let go.
    """
    _only_ours(name, where, root)
    return asking("bootout", f"{domain()}/{label(name)}")


def _let_go(name: str, said: Spoke, asking: Callable[..., Spoke] = ask) -> bool:
    """Has the machine really let go of this job?

    Three answers, not two. The bootout being accepted is one. A refusal followed by the
    machine saying plainly that it has no such job is another — that is a job it never
    had, and refusing to boot out something absent is not a reason to keep chasing it.
    Silence is the third, and it is *not* the second: a machine too busy to answer has
    told us nothing at all.
    """
    # An accepted bootout is a request taken, not a job released — launchd finishes in
    # its own time, and the plist was being deleted while it still held the job. So the
    # machine is asked, either way, until it says the job is gone.
    return _gone_from(name, asking)


def _only_ours(name: str, where: str | None = None, root: Path | None = None) -> None:
    """Refuse anything to do with a job this install did not write.

    Called by everything that reaches the machine. `install` did not, and so would boot
    out a job belonging to something else and then overwrite it in place — the exact
    destruction the rest of this module is careful about, reachable through the most
    ordinary verb there is.
    """
    path = job_path(name, where)
    if path.exists() and not ours(path, root):
        raise NotOurs(f"the job for '{name}' was not written by this install of rundesk")


def start(name: str, where: str | None = None, root: Path | None = None,
          asking: Callable[..., Spoke] = ask) -> Spoke:
    _only_ours(name, where, root)
    return asking("kickstart", f"{domain()}/{label(name)}")


def stop(name: str, where: str | None = None, root: Path | None = None,
         asking: Callable[..., Spoke] = ask) -> Spoke:
    """Ask the machine to stand it down, without forgetting the job."""
    _only_ours(name, where, root)
    return asking("kill", "SIGTERM", f"{domain()}/{label(name)}")


def ours(path: Path, root: Path | None = None) -> bool:
    """Is this job one *this install* wrote?

    A job named like ours is not necessarily ours. Anything else that names its jobs the
    same way — another install of rundesk, or another tool entirely — puts them in the
    same directory, so a job is ours only if it runs the command that lives in *this*
    install. Getting this wrong means `rundesk stop` standing down somebody else's live
    agents.
    """
    try:
        with open(path, "rb") as file:
            said = plistlib.load(file)
    except (OSError, ValueError):
        return False
    runs = said.get("ProgramArguments")
    if not isinstance(runs, list) or not runs:
        return False
    return str(runs[0]) == str((root or ROOT) / "rundesk")


def described(where: str | None = None, root: Path | None = None) -> list[str]:
    """Every gateway *this install* has given the machine a job for."""
    home = Path(os.path.expanduser(where or jobs_home()))
    if not home.is_dir():
        return []
    return sorted(
        path.name[len(PREFIX) + 1: -len(".plist")]
        for path in home.glob(f"{PREFIX}.*.plist")
        if ours(path, root)
    )


def exists(name: str, where: str | None = None) -> bool:
    """Is there a job of this name at all, whoever wrote it?

    Told apart from `known` on purpose: "there is no job" and "there is one, and it is
    not ours" send a reader somewhere completely different, and answering both with the
    same word is how `stop` came to report a job that plainly exists as not running.
    """
    return job_path(name, where).exists()


def known(name: str, where: str | None = None, root: Path | None = None) -> bool:
    """Does the machine have a job for this gateway, written by this install?"""
    path = job_path(name, where)
    return path.exists() and ours(path, root)


def take_back(
    name: str,
    where: str | None = None,
    root: Path | None = None,
    asking: Callable[..., Spoke] = ask,
    standing=None,
) -> bool:
    """Stop this gateway and take its job away, or say it would not let go (R-RM-9).

    What removal has to do before anything is deleted. A job outlives the command it
    names: the gateway it started keeps running, because deleting a program does not
    stop one, and the machine goes on trying to start it again — every few seconds, and
    again at every login — against a path that is no longer there. What is left behind
    is a running agent nobody can reach and a supervisor failing in a loop forever.

    **Two parties have to let go, and both are asked.** Judging this on the gateway
    process alone reported a name as taken back while the machine was still refusing to
    release its job — so an uninstall deleted the install and left the machine trying to
    start a command that was no longer there, every few seconds and again at every login.

    False leaves the description exactly where it is. It is the only thing that will find
    this gateway again: deleting it here left the first attempt reporting the name as
    stubborn and every attempt after it unable to see the gateway at all, with the thing
    itself still running.
    """
    from rundesk import gateway  # here, so this module imports on a machine without one

    standing = standing or gateway.standing
    said = remove(name, where, root, asking)
    deadline = time.monotonic() + SETTLE_SECONDS
    while standing(name).running and time.monotonic() < deadline:
        time.sleep(0.2)
    if standing(name).running or not _let_go(name, said, asking):
        return False
    job_path(name, where).unlink(missing_ok=True)
    return True


def take_all_back(
    where: str | None = None,
    root: Path | None = None,
    asking: Callable[..., Spoke] = ask,
    standing=None,
) -> tuple[list[str], list[str]]:
    """Stop every gateway this install is keeping, and take its job away (R-RM-9).

    Only jobs this install wrote. Returns what was taken back, and what would not stop.
    """
    taken, stubborn = [], []
    for name in described(where, root):
        try:
            (taken if take_back(name, where, root, asking, standing) else stubborn).append(name)
        except (NotOurs, NoSupervisor):
            continue
    return taken, stubborn
