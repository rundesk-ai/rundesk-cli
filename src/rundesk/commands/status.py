"""Whether the thing that runs agents is fit, rather than what any one agent is doing.

Two questions, two commands: `agents` answers "what do I have and what is it doing", and
this answers "is the install behind them able to start one". They were one command answering
neither.
"""

from __future__ import annotations

import argparse

from rundesk import ROOT, __version__
from rundesk import backup as backups
from rundesk import backups_home
from rundesk import standing
from rundesk.commands import _answered_within, _as_table

#: How long install health waits for backup storage to answer. A cloud-backed directory
#: can block inside the operating system indefinitely; status remains useful without it
#: and reports that one answer as unavailable (R-BKP-28).
BACKUP_STATUS_PATIENCE = 1.0


def cmd_status(_args: argparse.Namespace, gateways, machine, agents) -> int:
    """How rundesk itself and its current load stand on this machine.

    Two questions, two commands. `agents` answers "what do I have and what is it doing";
    this answers "is the thing that runs them fit". They were one command answering
    neither, because a list of gateways says nothing about whether the install behind them
    can start one.
    """
    unfit = gateways.fitness(ROOT)
    try:
        supervisor = "yes" if machine.available() else "no — nothing keeps an agent up here"
    except Exception:                                    # pragma: no cover - defensive
        supervisor = "?"
    names = standing.every_name(gateways, machine, agents)
    found = {name: standing.of(name, gateways, agents) for name in names}
    running = sum(1 for one in found.values() if one.running)
    working = 0
    turning = 0
    for name in names:
        run_home = agents.resolved(name).run
        working += len(gateways.what_is_working(name, run_home)) if found[name].running else 0
        turning += len(gateways.what_is_turning(name, run_home))
    _as_table(("WHAT", "IS"), [
        ("version", __version__),
        ("install", str(ROOT)),
        ("fit to run", "yes" if not unfit else f"no — {unfit}"),
        ("supervisor", supervisor),
        ("configured agents", str(len(agents.known()))),
        ("running gateways", str(running)),
        ("live processes", str(working + turning)),
        ("active turns", str(turning)),
        # Said here because "am I backed up" is a question about the install rather than
        # about any agent, and the answer somebody needs is not how many copies there are
        # but whether anything is still making them.
        ("backups", _how_backups_stand(machine)),
    ])
    return 1 if unfit else 0


def _how_backups_stand(machine) -> str:
    """Whether daily copies run and how many exist, without waiting forever (R-BKP-28)."""
    reached, count_kept = _answered_within(
        BACKUP_STATUS_PATIENCE,
        lambda: len(backups.every(backups_home())),
        "rundesk-backup-status",
    )
    if not reached:
        count_kept = None
    held = ("unavailable" if count_kept is None else
            (f"{count_kept} kept" if count_kept else "none yet"))
    try:
        daily = machine.keeps_backups()
    except Exception:                                    # pragma: no cover - defensive
        return held
    return f"{held}, daily {'on' if daily else 'off'}"
