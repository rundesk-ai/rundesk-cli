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

import importlib.util
import re
import sys
from pathlib import Path
from typing import Callable, List, Optional

from rundesk.core import config

#: What a step file is called: a number that orders it, then what it does.
NAMED = re.compile(r"^(\d{4})_([a-z0-9_]+)\.py$")

STEPS = Path(__file__).resolve().parent / "steps"


class Step:
    """One migration step: its id, the order it runs in, and the change it makes."""

    def __init__(self, at: Path, order: int, id: str):
        self.at = at
        self.order = order
        self.id = id

    def __repr__(self) -> str:
        return f"<step {self.id}>"

    def carry(self, data: Path) -> None:
        """Load the step and run it. Loaded when it is run, never imported at module level."""
        spec = importlib.util.spec_from_file_location(f"rundesk_step_{self.id}", self.at)
        if spec is None or spec.loader is None:
            raise Broken(f"{self.id} could not be loaded")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
            carry = getattr(module, "carry", None)
            if not callable(carry):
                raise Broken(f"{self.id} has no carry(data) to run")
            carry(data)
        finally:
            sys.modules.pop(spec.name, None)


class Broken(Exception):
    """A step that cannot be run at all, as opposed to one that ran and failed."""


def found(where: Optional[Path] = None) -> List[Step]:
    """Every step, in the order they run. Found rather than listed.

    A file that is not named like a step is ignored rather than refused, so `__init__.py` and
    anything an editor leaves behind cost nothing.
    """
    steps = []
    for at in sorted((where or STEPS).glob("*.py")):
        said = NAMED.match(at.name)
        if said:
            steps.append(Step(at, int(said.group(1)), f"{said.group(1)}_{said.group(2)}"))
    return sorted(steps, key=lambda step: step.order)


def newest(where: Optional[Path] = None) -> Optional[str]:
    """The id of the last step this release ships, or `None` when it ships none."""
    steps = found(where)
    return steps[-1].id if steps else None


def outstanding(applied: Optional[str], where: Optional[Path] = None) -> List[Step]:
    """The steps that have not run yet, given how far the install has been carried.

    An install stamped with a step this release has never heard of is **going backwards** — it was
    carried by a newer rundesk than the one now asking. Refused rather than guessed at: running an
    older release's steps over a newer release's layout is how data gets damaged.
    """
    steps = found(where)
    if applied is None:
        return steps
    ids = [step.id for step in steps]
    if applied not in ids:
        raise Broken(
            f"this install was carried to {applied}, which this rundesk does not ship — "
            "it has been moved forward by a newer release, and going backwards is not supported")
    return steps[ids.index(applied) + 1:]


def carry(data: Path, where: Optional[Path] = None,
          saying: Optional[Callable[[str], None]] = None) -> Optional[str]:
    """Run every step that has not run, stamping each one as it lands. `None` when all is well.

    **Stamped one at a time, immediately after the step it records.** A run that dies halfway has
    therefore recorded exactly the steps that finished, so whatever picks up next carries on from
    there rather than starting again over changes already made.

    Stops at the first step that fails and says which — the ones after it are written expecting it
    to have happened, so carrying on would apply them to a shape they were not written for.
    """
    said = saying or (lambda _line: None)
    settled = config.read(data)
    try:
        waiting = outstanding(settled.get("migration"), where)
    except Broken as why:
        return str(why)

    if not waiting:
        return None

    for step in waiting:
        said(f"carrying {step.id}")
        try:
            step.carry(data)
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
