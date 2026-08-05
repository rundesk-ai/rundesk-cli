"""Carrying an install forward when a newer release expects something different.

There are **two levels of migration**, and this is the first of them:

1. **Install migrations — here.** A change to the install as a whole: a directory that moved, a
   configuration value whose meaning changed, something a release needs laid down before it can run.
   One step per file in `steps/`, and they run once each, in order.
2. **Agent migrations — not this module.** What one agent keeps, carried inside that agent's own
   records. A different level with a different unit of failure: an install carries once, an agent
   carries per agent, and one agent that cannot be moved must not stop the others.

## How a step is found and recorded

A step is a file in `steps/` named `NNNN_what_it_does.py`, and it is **found rather than listed** —
there is no table of steps to forget to update. It runs in the order its number gives.

What has run is one value: `migration` in `data/config.json`, holding the id of the **last step
applied**. Steps run in order, so how far the install has got is the only thing worth recording, and
there is no second list to disagree with the first.

That works because of one rule with no exceptions: **a step that has shipped is never renumbered,
never renamed, and never edited.** Its id is how every install on every machine knows whether it has
run. A step that needs changing is a new step.

## A fresh install has nothing to migrate

Installing for the first time **stamps the newest step without running anything**. There is no old
layout to move: the steps describe changes *from* previous releases, and running them against a
directory that was created correctly a second ago is at best wasted work and at worst damage.

## What a step may assume, and what it may not

A step is handed the install's `data/` directory and nothing else. It may find the thing it was
written to change already gone — because an owner tidied it, or because a half-finished run got that
far — so **every step is written to be safe to run against an install that does not need it**.
"""

from pathlib import Path
from typing import Callable, List, Optional

from rundesk.core import config
from rundesk.utils import scripts

STEPS = Path(__file__).resolve().parent / "steps"

#: One step: where it is, the order it runs in, and its id.
#:
#: `utils.scripts`' own record, named here as well. Finding numbered scripts in a directory, putting
#: them in order and refusing two that share a number is the same problem for an install as it is
#: for an agent, and neither of them is the interesting part — what differs is what a step is handed
#: and how what has run is written down, and that is what stays in each runner.
Step = scripts.Script

#: A step that cannot be run at all, as opposed to one that ran and failed. `utils.scripts`' answer,
#: named here too so a caller of this module never has to know which file the mechanism lives in —
#: the same courtesy `config` does for `files.Unreadable`.
Broken = scripts.Broken


def found(where: Optional[Path] = None) -> List[Step]:
    """Every step this release ships, in the order they run. Found rather than listed.

    The rule that makes the id trustworthy — **two steps may not share a number** — is enforced by
    `utils.scripts` and matters here for a reason that is this module's own: how far an install has
    been carried is *one* id, so an install stamped with the first of two would run the second, and
    one stamped with the second would skip the first, silently and for good.
    """
    return scripts.found(where or STEPS)


def newest(where: Optional[Path] = None) -> Optional[str]:
    """The id of the last step this release ships, or `None` when it ships none."""
    steps = found(where)
    return steps[-1].id if steps else None


def outstanding(applied: Optional[str], where: Optional[Path] = None) -> List[Step]:
    """The steps that have not run yet, given how far the install has been carried.

    An install stamped with a step this release does not ship is refused, and **the sentence names
    both ways that happens** rather than only the first. Either a newer rundesk carried this install
    and going backwards is not supported, or a step that had already shipped was deleted or renamed
    in this copy — which the rules forbid and nothing prevents, and which is much the likelier of
    the two for a developer to have just done. Refused either way: running these steps over a layout
    that was carried past them is how data gets damaged.

    **Which steps have run is decided by their number, not by their position in this list**, and
    that is the whole of the append-only rule: everything numbered at or below the recorded id has
    run.

    **One id is the whole state here, and that is the design rather than a smaller version of the
    agent level's.** An install is one thing with one history, and it keeps no database — there is
    nothing to have a table in, and a list would record the same single fact in more words. An agent
    is one of many, each carried on its own and each able to fail without the others, so each keeps
    its own log of what ran in the table it already has. Two different shapes because they answer
    two different questions, not because one of them settled for less.

    What follows from one id is that the numbering rule is a rule rather than a check: a step that
    needs changing is a new step, numbered above every number any release has used. An install that
    ran `0001` and `0010` and one that ran `0001`, `0005` and `0010` both record `0010`, so nothing
    here can tell them apart, and a step back-filled below the mark would never run on an install
    already carried past it. The agent level *can* check its own equivalent, because a table can be
    asked which rows are in it — see `agents.migration.Backfilled`.
    """
    steps = found(where)
    if applied is None:
        return steps
    ids = [step.id for step in steps]
    if applied not in ids:
        raise Broken(
            f"this install was carried to {applied}, which this rundesk does not ship — either it "
            "has been moved forward by a newer release, or a step that had already shipped was "
            "deleted or renamed in this copy of rundesk; going backwards is not supported")
    carried = steps[ids.index(applied)]
    return [step for step in steps if step.order > carried.order]


def carry(data: Path, where: Optional[Path] = None,
          saying: Optional[Callable[[str], None]] = None) -> Optional[str]:
    """Run every step that has not run, stamping each one as it lands. `None` when all is well.

    **Stamped one at a time, immediately after the step it records.** A run that dies halfway has
    therefore recorded exactly the steps that finished, so whatever picks up next carries on from
    there rather than starting again over changes already made.

    Stops at the first step that fails and says which — the ones after it are written expecting it
    to have happened, so carrying on would apply them to a shape they were not written for.

    **A sentence, never an exception**, and the read of the configuration is inside the `try` for
    that reason: it was outside, so a `data/config.json` that is there and cannot be read raised
    straight past this contract and out of whatever was carrying the install. Its sibling at the
    agent level already reads what has run inside its own `try`.
    """
    said = saying or (lambda _line: None)
    try:
        settled = config.read(data)
        waiting = outstanding(settled.get("migration"), where)
    except (Broken, config.Unreadable) as why:
        return str(why)

    if not waiting:
        return None

    for step in waiting:
        said(f"carrying {step.id}")
        try:
            scripts.carrying(step, "rundesk_step")(data)
        except Exception as why:                      # noqa: BLE001 — a step is arbitrary code
            return f"{step.id} did not finish: {why}"
        config.stated("migration", step.id, data)
    return None


def stamp_without_running(data: Path, where: Optional[Path] = None) -> None:
    """Record every step as done without running one. What a **fresh install** does.

    There is nothing to carry: the directories were made correctly a moment ago, and the steps
    describe changes from releases this install never had.
    """
    config.stated("migration", newest(where), data)
