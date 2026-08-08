"""A directory of numbered scripts, found in order, and one of them loaded to run.

Two things in this product carry something forward a step at a time — an install, and each agent —
and both answer the same three questions: which scripts are there, what order do they run in, and
how is one of them loaded and called without putting it on the import path. That part is identical
and has nothing to do with what is being carried, so it is here rather than written twice.

What is *not* here is what each runner does with the answer. An install records how far it has got
as one value and an agent records a row per step; an install is handed a directory and an agent is
handed an open transaction. Those differ for good reasons and stay with their own runner.

**A script is found, never listed.** There is no table to forget to update, which is the whole point:
a step added to a directory runs the day it lands.

**Two scripts may not share a number.** How far something has been carried is decided by the order
they run in, and two files numbered the same have no order except the one their filenames happen to
give. That is not a hypothetical mistake — it is what happens the first time two branches each add a
step and both reach for the next free number. Refused here, while it is still a broken checkout,
rather than after it has shipped and every machine has already made a different arbitrary choice.

**Loaded when it is run, and never left on the import path.** A script is arbitrary code from a
directory, not a module of this product's; importing them all to look at them would run every one of
them, and leaving one in `sys.modules` would let the next thing that imported that name get it.

Knows nothing about rundesk.
"""

import importlib.util
import re
import sys
from pathlib import Path
from typing import Callable, List, NamedTuple, Optional

#: What a script is called: a number that orders it, then what it does.
NUMBERED = re.compile(r"^(\d{4})_([a-z0-9_]+)\.py$")


class Broken(Exception):
    """A script that cannot be run at all, as opposed to one that ran and failed.

    The distinction is the useful part: the first is a checkout somebody has to fix, and the second
    is a machine somebody has to look at.
    """


class Script(NamedTuple):
    """One numbered script: where it is, the order it runs in, and its id.

    A record rather than an object with a life of its own, and immutable on purpose: an id is how
    every machine knows whether that script has already run, so nothing should be able to change one
    after it has been found.
    """

    at: Path
    order: int
    id: str

    def __repr__(self) -> str:
        return f"<script {self.id}>"


def found(where: Path) -> List[Script]:
    """Every script in `where`, in the order they run.

    A file that is not named like one is ignored rather than refused, so `__init__.py` and anything
    an editor leaves behind cost nothing. A directory that is not there has no scripts in it, which
    is an answer rather than a failure — a release may legitimately ship none.
    """
    scripts = []
    try:
        there = sorted(where.glob("*.py"))
    except OSError:
        return []
    for at in there:
        said = NUMBERED.match(at.name)
        if said:
            scripts.append(Script(at, int(said.group(1)), f"{said.group(1)}_{said.group(2)}"))
    scripts.sort(key=lambda script: script.order)
    for before, after in zip(scripts, scripts[1:]):
        if before.order == after.order:
            raise Broken(
                f"{before.id} and {after.id} are both numbered {before.order:04d}, and how far "
                "something has been carried is decided by the order they run in — there is no "
                "order between them")
    return scripts


def carrying(script: Script, called: str, wanted: str = "carry") -> Callable[..., None]:
    """Load a script and hand back the one function it exists to run.

    `called` is what the module is known as while it loads — a prefix, so two runners loading the
    same number cannot collide with each other. The arguments are the caller's to supply, because
    that is exactly the part the two runners disagree about.

    Taken out of `sys.modules` before this returns, not after the call: once the module object is
    built, keeping the name registered serves nothing and risks handing this script to whatever
    imports that name next. The module object stays alive because the function returned holds it.
    """
    where = f"{called}_{script.id}"
    spec = importlib.util.spec_from_file_location(where, script.at)
    if spec is None or spec.loader is None:
        raise Broken(f"{script.id} could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[where] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(where, None)

    run: Optional[Callable[..., None]] = getattr(module, wanted, None)
    if not callable(run):
        raise Broken(f"{script.id} has no {wanted}() to run")
    return run
