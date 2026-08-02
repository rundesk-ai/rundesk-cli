"""The command groups: one module per family of verbs, and the little they share.

A layer of its own. Everything under `src/rundesk/` proper holds one concern and knows
nothing of how it was invoked; a module in here is the exception on purpose — it takes an
`argparse.Namespace` and hands back an exit code, which is what a command *is*. `cli.py`
above it owns the parser and the dispatch and nothing else; the modules below it own locks,
records and process groups and have never heard of a flag.

What each group acts on — the gateways, the machine, the agents, the skills — arrives as an
argument from `cli.main`, so every verb is exercised with none of them anywhere near it.

This file holds only what more than one group needs and nothing below the surface wants:
how a table is printed, how a change is written into an agent's log, and how a call that
may block inside the operating system is given up on.
"""

from __future__ import annotations

import queue
import sys
import threading


def _as_table(head: tuple, rows: list) -> None:
    """Columns wide enough for what is in them. Written once, so the two things that
    list something in columns cannot come to disagree about how."""
    if not rows:
        return
    widths = [max(len(row[i]) for row in [head] + rows) for i in range(len(head))]
    for row in [head] + rows:
        print("  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip())


def _note(gateways, name: str, said: str, whose=None) -> int:
    """Say what was changed, in the log of the agent it was changed for, and say so out
    loud when it could not be written (R-GW-37).

    A schedule that appears or vanishes is as much a part of what happened to an agent
    as anything it ran, and the log is the only account that outlives the gateway. The
    change itself stands either way — it is already on disk by the time this is called,
    and unwinding a good mutation because its audit line failed would be the worse of
    the two outcomes. What must not happen is the command reporting a plain success:
    that is a mutation and its history disagreeing, with nobody told.

    The code it returns is what the command exits with, so a caller adds it to nothing
    and simply returns it.
    """
    logs = whose.logs if whose else None
    why = gateways.note(name, said, logs)
    if why is None:
        return 0
    print(f"{name}: WARNING — change applied, but not logged: "
          f"{gateways.log_path(name, logs)}: {why}", file=sys.stderr)
    return 1


def _answered_within(patience: float, work, called: str) -> tuple:
    """Do something that may block inside the operating system, and give up on it.

    Returns `(True, what it gave back)`, or `(False, None)` when it did not answer in
    time or failed. **The bound belongs to every command that touches the directory, not
    only to health (R-BKP-29).** `status` grew this guard first, for a backup directory
    symlinked into cloud storage that blocks in `opendir` forever; `backups` then sat on
    the identical call with no bound at all, which is the one command that cannot answer
    without it.

    A Python thread cannot interrupt an operating-system `opendir`, but a daemon does not
    keep this one-shot CLI process alive: the blocked call is abandoned with the process
    rather than turning one unreachable filesystem into a command that never returns.
    """
    answered: queue.Queue = queue.Queue(maxsize=1)

    def carry() -> None:
        try:
            answered.put((True, work()))
        except BaseException:                           # pragma: no cover - defensive boundary
            answered.put((False, None))

    threading.Thread(target=carry, name=called, daemon=True).start()
    try:
        return answered.get(timeout=patience)
    except queue.Empty:
        return (False, None)
