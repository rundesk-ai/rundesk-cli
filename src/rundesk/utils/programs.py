"""Running another program, and the three answers `subprocess` collapses into one.

A program that was asked to run can end three ways, and they are not degrees of the same thing:

**It ran, and said what it thought.** There is an exit code, and the code is the answer.

**It never started.** The file is not there, or is not executable, or the interpreter behind it is
missing. There is no exit code, because nothing ran — and reporting this as a failing exit code says
the program ran and disagreed, which is a different fact about the machine and leads somewhere else.

**It started and would not finish.** Something is wrong that waiting will not fix, and the output so
far is the only evidence there is.

`subprocess` gives the first as an exit code, the second as an exception, and the third as a
different exception, and every caller that writes `except Exception: return 1` has just told
somebody their program ran and failed when it was never on the machine. So `Ran` carries all three,
and `trouble` is the field that says which.

## Two things it will not let a caller forget

**Standard input is never inherited.** A program that reads from a terminal nobody is watching waits
for ever, and it waits holding whatever its parent was holding. Closed, always — a caller that needs
to send something sends it deliberately.

**There is always a ceiling.** A wait with no end is the failure this project refuses everywhere it
appears: the command somebody typed simply never returns, and nothing in the output says why. The
ceiling is an argument because how long is too long belongs to the caller — proving an installed
command answers and waiting for a release to download are not the same patience.

Knows nothing about rundesk.
"""

import contextlib
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Dict, NamedTuple, Optional, Sequence

#: What a program that never started, or would not finish, has instead of an exit code.
DID_NOT_START = "did not start"
WOULD_NOT_FINISH = "would not finish"


class Ran(NamedTuple):
    """What became of a program, in the three parts that can differ.

    `trouble` is the field to read first. While it is `None` the program ran and `code` is its
    answer; once it is set there is no exit code at all, and a caller treating `code` as `0`-or-not
    would be reading a number nothing produced.

    **There is deliberately no `worked` shortcut.** One existed and was removed: it answered `False`
    both for a program that ran and disagreed and for one that was never on the machine, which is
    the single distinction this whole type exists to keep. Both real callers had already routed
    around it and asked `trouble` then `code` themselves — when the people who must get it right
    avoid the convenience, the convenience is a trap for whoever does not know to.
    """

    code: Optional[int]
    out: str
    err: str
    trouble: Optional[str]

    def __repr__(self) -> str:
        return f"<ran {self.trouble or self.code}>"


def run(argv: Sequence[str], waiting: float, where: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None) -> Ran:
    """Run a program and hand back all three answers. Never raises for anything the program did.

    `waiting` is required rather than defaulted, so no caller arrives at a wait with no end by
    forgetting an argument. What comes back is text, because every caller of this so far reads it as
    lines a person wrote.

    An exception from the program itself is not passed on: the whole point is that "it was not
    there" is an answer to be reported, not a traceback to be caught again at every call site.
    """
    try:
        ended = subprocess.run(
            [str(one) for one in argv],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=waiting,
            cwd=str(where) if where else None,
            env=env,
        )
    except subprocess.TimeoutExpired as why:
        # What it managed to say before it stopped answering is the only evidence there is, so it
        # comes back rather than being dropped with the exception.
        return Ran(None, _said(why.stdout), _said(why.stderr),
                   f"{WOULD_NOT_FINISH} within {waiting:g} seconds")
    except (OSError, ValueError) as why:
        return Ran(None, "", "", f"{DID_NOT_START}: {why}")
    return Ran(ended.returncode, ended.stdout, ended.stderr, None)


def _said(maybe) -> str:
    """What a timed-out program had written, whichever way this Python hands it over.

    `TimeoutExpired` carries `bytes` on some versions and `str` on others depending on how the run
    was asked for, and `None` when it wrote nothing at all. A caller should not have to know which.
    """
    if maybe is None:
        return ""
    return maybe.decode("utf-8", "replace") if isinstance(maybe, bytes) else str(maybe)


# ---------------------------------------------------------------------------------------------
# A program that keeps running, which is a different problem from one that answers and stops.
# ---------------------------------------------------------------------------------------------
#
# `run` above waits for an answer. Everything below is for a program that is not going to give one
# for hours: it is started, it is watched, and eventually it is stopped. Four things make that
# different, and all four are things the build this replaces got wrong at least once.
#
# **It is started in a session of its own.** `start_new_session=True` gives it a new session and a
# new process group, and it becomes the leader. That one flag is what makes the rest possible: a
# program like this starts programs of its own, and signalling the *group* reaches all of them.
# Without it, stopping a gateway leaves whatever it spawned running — with nothing left holding the
# ids, so nobody can ever stop them.
#
# **Its output goes to a file, never to a pipe.** A pipe nobody is draining fills, and a program
# writing into a full pipe blocks for ever — a deadlock that looks exactly like a hang, and appears
# only once the thing has been running long enough to say 64KB.
#
# **A pid is not an identity.** The number is reused. A recorded pid that is alive today may be
# somebody else's process, and signalling it would kill a stranger's program. Nothing here can solve
# that alone, so nothing here pretends to: `alive` answers about a number, and whoever recorded the
# number owns proving it is still the same program.
#
# **Stopping is asked before it is insisted on.** A program gets a chance to finish what it was
# doing, and only then is it taken away.

#: How the group is asked, and then told. In this order, never the other way round.
GENTLY = signal.SIGTERM
FIRMLY = signal.SIGKILL

#: How often a wait for something to stop looks again.
LOOKING_AGAIN = 0.05


def start(argv: Sequence[str], log: Path, where: Optional[Path] = None,
          env: Optional[Dict[str, str]] = None) -> int:
    """Start a long-lived program in a session of its own and hand back its process id.

    Everything it writes is appended to `log`, which is opened here rather than left to the caller
    so that no version of this ends up handing the program a pipe.

    The file is opened for appending on purpose: a restart adds to the history rather than replacing
    it, and history is most of what a log is for.
    """
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8") as writing:
        # A list, never a string through a shell: nothing here is ever word-split or expanded.
        started = subprocess.Popen(
            [str(one) for one in argv],
            stdin=subprocess.DEVNULL,
            stdout=writing,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            cwd=str(where) if where else None,
            env=env,
        )
    return started.pid


def alive(pid: int) -> bool:
    """Whether a process with that id is running now.

    Signal `0` asks the kernel without sending anything. A process that is running but belongs to
    somebody else answers `EPERM`, which is still an answer: something is there.

    **This says a process exists, not that it is the one you meant.** Ids are reused.
    """
    if pid <= 1:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def stop(pid: int, gently_for: float, firmly_for: float = 5.0) -> str:
    """Stop a program and everything it started. `""` when it is gone, otherwise why it is not.

    Asked with `SIGTERM` first and given `gently_for` to finish; told with `SIGKILL` after. Sent to
    the process *group*, so what the program started stops with it rather than being orphaned.

    A program that is already gone is not a failure — it is the state that was asked for.
    """
    if pid <= 1:
        return f"{pid} is not a process this may signal"
    try:
        group = os.getpgid(pid)
    except ProcessLookupError:
        return ""
    except PermissionError as why:
        return f"{pid} belongs to somebody else ({why})"

    # `killpg` on our own group signals this very process and everything beside it. It is reachable
    # by an honest mistake — a recorded id that was reused by something started from this shell —
    # and the result is the command killing itself mid-sentence.
    if group == os.getpgrp():
        return f"{pid} is in this command's own process group, and stopping it would stop this"

    for how, patience in ((GENTLY, gently_for), (FIRMLY, firmly_for)):
        trouble = _signalled(group, how)
        if trouble:
            return trouble
        if _gone_within(pid, patience):
            return ""
    return f"{pid} was still running after being asked and then told to stop"


def _signalled(group: int, how: int) -> str:
    """Send one signal to a whole process group. `""` when it landed or there was nobody left."""
    try:
        os.killpg(group, how)
    except ProcessLookupError:
        return ""
    except PermissionError as why:
        return f"process group {group} could not be signalled ({why})"
    return ""


def _gone_within(pid: int, patience: float) -> bool:
    """Wait for a process to disappear, reaping it if it happens to be ours.

    **Reaped, or it never disappears.** A child this process started stays in the table as a zombie
    until somebody collects it, and a zombie answers signal `0` — so a stop that only watched would
    wait out its whole ceiling and then report a program still running that had already exited.
    `ECHILD` means it was not our child, which is ordinary: it may have been started by an earlier
    run of the command entirely.
    """
    ceiling = time.monotonic() + patience
    while True:
        with contextlib.suppress(ChildProcessError):
            os.waitpid(pid, os.WNOHANG)
        if not alive(pid):
            return True
        if time.monotonic() >= ceiling:
            return False
        time.sleep(LOOKING_AGAIN)
