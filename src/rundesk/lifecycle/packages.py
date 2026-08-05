"""The packages an install keeps for the programs it starts, and nothing else.

**Nothing under `src/rundesk/` may import one of these.** The product's own code is the standard
library and stays that way; what needs a package is an *adapter*, which is a separate program on the
far side of a pipe. Reaching Discord needs `discord.py`, and the only reason that is compatible with
a product whose own code imports nothing is that the import happens in another process.

So this exists for exactly one reason: an adapter cannot import a package nobody installed. The pin
in `requirements.txt` was carried for a release with nothing building from it, which meant a channel
could be configured and could never start — the install reported a success, and the failure arrived
later, somewhere else, wearing an `ImportError`.

## Where it goes, and why there

`app/.venv`, inside the tree an update replaces. Two things follow from that and both are wanted:
the packages belong to the release that asked for them, and an update that lands a new tree gets a
new environment built from that tree's own requirements rather than inheriting the last one's.

`lifecycle.tree` already refuses to *copy* a `.venv`, which is right and is the other half of this:
an environment is built at its destination, never carried there. One built on a different machine,
or under a different interpreter, is a directory of absolute paths that do not resolve.

## An empty file means no environment at all

That is the state to return to if a dependency ever stops earning its place, and it is checked
rather than assumed: a `requirements.txt` holding only comments is empty, and nothing is built.

## What a failure here is, and what it is not

**It is not a failed install.** rundesk itself runs on the standard library, so a machine with no
network has a working install and no channels — which is a true thing to say and a false reason to
report that the install broke. The caller reports it and goes on.

**It is also never silence.** An install that could not build the environment says so, names what
to run to try again, and `channels doctor` says the same thing later from the other end.

May depend on `core` and `utils`.
"""

import sys
from pathlib import Path
from typing import Callable, List, Optional

from rundesk.utils import programs

#: What the release says it needs, at the top of the tree that landed.
WANTED_IN = "requirements.txt"

#: Where the environment stands, inside the tree an update replaces.
VENV = ".venv"

#: How long making an empty environment may take. It copies an interpreter and writes a handful of
#: scripts; a minute is already generous, and the ceiling is here because nothing that runs during
#: an install may wait with no end.
MAKING_WITHIN = 180.0

#: How long fetching may take. Long, because it is somebody else's network and a wheel that has to
#: be built from source is minutes rather than seconds — and finite, because a person is waiting.
FETCHING_WITHIN = 900.0


def wanted(app: Path) -> List[str]:
    """What this release says it needs, one requirement per entry. `[]` when it needs nothing.

    Comments and blank lines are not requirements, which is what makes "an empty file" a state
    somebody can actually reach — the file this product ships is mostly explanation.
    """
    try:
        said = (app / WANTED_IN).read_text(encoding="utf-8")
    except OSError:
        return []
    return [line.strip() for line in said.splitlines()
            if line.strip() and not line.strip().startswith("#")]


def where(app: Path) -> Path:
    """The environment for this release, inside the tree an update replaces."""
    return app / VENV


def interpreter(app: Path) -> Path:
    """The interpreter inside that environment, whether or not it is there yet."""
    return where(app) / "bin" / "python3"


def ready(app: Path) -> bool:
    """Whether the packages this release asked for could be imported by something starting now.

    Asked of the disk rather than remembered from the install, because an install is not the only
    thing that can have happened since: a tree can be replaced, a directory removed, a volume
    unmounted. Anything deciding whether a channel can start has to ask now.
    """
    return not wanted(app) or interpreter(app).is_file()


def built(app: Path, running: Optional[Callable[..., programs.Ran]] = None) -> str:
    """Build the environment this release asked for. `""` when there is nothing to do or it worked.

    Otherwise a sentence saying what went wrong, for a caller to report without failing on — see
    the module docstring on why a machine with no network has a working install and no channels.

    **Made afresh rather than updated in place.** `pip install` into an environment left by a
    previous release leaves that release's packages standing beside this one's, so what is installed
    stops being what any `requirements.txt` says. The directory is inside the tree an update
    replaces, so there is nothing here worth keeping across one.

    Resolved inside the body rather than bound in the signature, so a suite can drive the whole of
    this with no network anywhere near it.
    """
    needs = wanted(app)
    if not needs:
        return ""
    run = running or programs.run

    made = run([sys.executable, "-m", "venv", "--clear", str(where(app))], MAKING_WITHIN)
    if made.trouble or made.code != 0:
        return _why("the environment for them could not be made", made)

    got = run([str(interpreter(app)), "-m", "pip", "install", "--disable-pip-version-check",
               "--quiet", "-r", str(app / WANTED_IN)], FETCHING_WITHIN)
    if got.trouble or got.code != 0:
        return _why(f"{len(needs)} package(s) could not be fetched", got)

    # Asked of the disk afterwards rather than inferred from an exit code. A `pip` that answered
    # `0` and left nothing runnable is the exact shape of a success nobody earned.
    if not interpreter(app).is_file():
        return "the environment was made and holds no interpreter"
    return ""


def _why(said: str, ran: programs.Ran) -> str:
    """One sentence, carrying the last thing the program managed to say.

    Bounded, because this ends up on somebody's terminal: `pip` writes a great deal when it fails,
    and the useful part is the end of it.
    """
    lines = [line.strip() for line in (ran.err or ran.out).splitlines() if line.strip()]
    ending = f" — {lines[-1][:200]}" if lines else ""
    return f"{said}{ending}" if not ran.trouble else f"{said} — {ran.trouble}"
