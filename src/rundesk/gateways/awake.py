"""Keep a Mac awake for exactly as long as a gateway is running.

macOS already ships the program that owns this policy: ``/usr/bin/caffeinate``. Asking it for an
idle-system-sleep assertion with ``-i`` keeps the machine available without keeping the display on,
and ``-w`` ties that assertion to the gateway's pid. The latter is the crash guarantee: when a
gateway is killed too abruptly to unwind a context manager, caffeinate still observes the pid going
away and releases the assertion rather than becoming an orphan that keeps the machine awake for
ever.

**One gateway owns one assertion.** There is no shared counter and no persisted state to race:
several gateways may each hold the same kind of assertion, and macOS may idle-sleep again only after
the last one is released. A shared keeper would need a second long-lived process merely to decide
whether the first long-lived processes exist.

This is gateway domain rather than a utility. It knows why the machine is being kept awake, when
that promise begins, and that losing it is a fault worth restarting a gateway for.
"""

import contextlib
import errno
import os
import platform
import subprocess
import time
from typing import Callable, Iterator, Optional, Sequence

#: The system program documented by ``caffeinate(8)`` on every supported Mac. An absolute path is
#: the guarantee that a gateway started by launchd and one started in a terminal ask the same
#: program, whatever either one's ``PATH`` contains.
CAFFEINATE = "/usr/bin/caffeinate"
PMSET = "/usr/bin/pmset"

#: Killing this helper takes no work away: it holds one kernel assertion and nothing else. A hard
#: stop also avoids inheriting an ignored SIGTERM from a gateway that has already begun shutting
#: down, which can survive an ``exec`` and otherwise leave a helper that cannot be ended politely.
REAP_WITHIN = 1.0

#: A process existing is not yet proof that its power assertion has reached macOS. Publishing is
#: normally visible on the first read; this ceiling makes a machine under login-time load a bounded
#: retry rather than either a false LIVE or a start that hangs for ever.
PUBLISH_WITHIN = 5.0
ASK_WITHIN = 1.0
LOOKING_AGAIN = 0.05

Starting = Callable[[Sequence[str]], subprocess.Popen]
Proving = Callable[[subprocess.Popen], bool]
Guard = Optional[subprocess.Popen]


class NotPreventingSleep(Exception):
    """A Mac permanently cannot establish its idle-system-sleep assertion."""


class TryAgain(NotPreventingSleep):
    """The assertion failed for a reason a fresh gateway start may clear."""


@contextlib.contextmanager
def while_running(system: Optional[str] = None,
                  starting: Optional[Starting] = None,
                  proving: Optional[Proving] = None) -> Iterator[Guard]:
    """Prevent idle system sleep on macOS until this context ends.

    Other platforms yield ``None`` and do nothing. ``system`` and ``starting`` are seams for a
    suite, resolved inside the function so a test never starts the machine's real caffeinate and a
    long-imported default never holds a collaborator nobody can replace.

    Starting successfully is not enough: a helper which exited at once established no durable
    guarantee, and one which has only just exec'd may not have published its assertion yet. The
    helper is proved alive and the assertion is read back from macOS before the caller may report
    the gateway online. The caller keeps proving the returned guard on each beat with
    :func:`proved`.
    """
    this_system = platform.system() if system is None else system
    if this_system != "Darwin":
        yield None
        return

    begin = _started if starting is None else starting
    argv = (CAFFEINATE, "-i", "-w", str(os.getpid()))
    try:
        guard = begin(argv)
    except OSError as why:
        # A missing or forbidden system binary will be exactly the same on every launchd retry, so
        # it is a refusal. Everything else — especially the process/file/memory ceilings reached
        # when many gateways start together at login — is a fault a later start may clear. Unknown
        # is retryable rather than a permanent instruction to leave this gateway down for ever.
        raise _could_not_start(CAFFEINATE, why) from why

    try:
        proof = _published if proving is None else proving
        ceiling = time.monotonic() + PUBLISH_WITHIN
        while True:
            proved(guard)
            try:
                if proof(guard):
                    break
            except OSError as why:
                raise _could_not_start(PMSET, why) from why
            if time.monotonic() >= ceiling:
                raise TryAgain(f"{CAFFEINATE} did not publish its idle-system-sleep assertion "
                               f"within {PUBLISH_WITHIN:g} seconds")
            time.sleep(LOOKING_AGAIN)
        yield guard
    finally:
        _ended(guard)


def proved(guard: Guard) -> None:
    """Prove the assertion is still held, or raise the fault a supervisor can clear.

    ``None`` is the complete non-macOS answer. On a Mac the child staying alive is the observable
    half of caffeinate's contract; if it ends, continuing to call the gateway live would promise
    protection the machine no longer has.
    """
    if guard is None:
        return
    code = guard.poll()
    if code is not None:
        raise TryAgain(f"{CAFFEINATE} exited with status {code}")


def _started(argv: Sequence[str]) -> subprocess.Popen:
    """Start the system helper with no terminal or pipe it could ever wait on."""
    return subprocess.Popen([str(one) for one in argv], stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            close_fds=True, start_new_session=True)


def _published(guard: subprocess.Popen) -> bool:
    """Whether macOS names this exact helper as holding the promised assertion."""
    try:
        read = subprocess.run([PMSET, "-g", "assertions"], stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                              errors="replace",
                              timeout=ASK_WITHIN, check=False)
    except subprocess.TimeoutExpired:
        return False
    if read.returncode != 0:
        return False
    owns = f"pid {guard.pid}(caffeinate)"
    return any(owns in line and "PreventUserIdleSystemSleep" in line
               for line in read.stdout.splitlines())


def _could_not_start(program: str, why: OSError) -> NotPreventingSleep:
    """Classify a stable machine refusal apart from pressure a fresh start may clear."""
    permanent = (errno.ENOENT, errno.EACCES, errno.EPERM, errno.ENOEXEC, errno.ENOTDIR)
    failed = NotPreventingSleep if why.errno in permanent else TryAgain
    return failed(f"{program} did not start: {why}")


def _ended(guard: subprocess.Popen) -> None:
    """End and reap this gateway's helper. Never hide the gateway's own outcome.

    ``-w`` is what handles a gateway killed before this runs. This path matters for a graceful
    stop and especially for ``exec``-based restart, where the gateway keeps the same pid and an old
    helper would otherwise keep waiting beside the new one.
    """
    with contextlib.suppress(OSError):
        if guard.poll() is None:
            guard.kill()
    with contextlib.suppress(OSError, subprocess.TimeoutExpired):
        guard.wait(timeout=REAP_WITHIN)
