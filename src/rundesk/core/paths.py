"""Where an install keeps everything — one root, and every other place derived downward from it.

This module is the decision the rebuild exists to get right. The build it replaces resolved its
locations from a dozen independent environment variables — the install directory, the data directory,
backups, agents, run state, logs, jobs, secrets, the skill library, the scripts directory — each with
its own default under the owner's home. Redirecting eleven of them still resolved the twelfth to the
live install, and that is not a hypothetical: it deleted an owner's built-in skills, wrote a real
credential into their secrets, and unregistered the job that kept their machine updating itself. Every
one of those was somebody who believed they had redirected everything.

So there is **one** variable, `RUNDESK_HOME`, and everything else is a function of it. A partial
redirect is not something you can express, and isolating a run is one decision rather than twelve.

Two rules hold this together, and both were paid for:

**Resolved on every call, never cached at import.** Binding a location once, when the module is first
imported, is how a suite comes to write into the real install: the test sets the variable in `setUp`,
long after the value it is trying to change was already decided.

**Where the program stands never answers where the data stands.** They are different questions. A
checkout install has the program in a developer's source tree while the data belongs under the owner's
home, so deriving one from the other is right exactly until somebody runs the command from a checkout.
"""

import os
from pathlib import Path

#: What the root is called in the environment, and the only location this product reads.
HOME_IS = "RUNDESK_HOME"

#: Where an install stands when nobody says otherwise.
DEFAULT_HOME = "~/.rundesk"


class Refused(Exception):
    """A root that must not be used, named with why.

    Raised rather than resolved, because the alternative is a command that carries on against a
    directory it should never have touched. The installer this replaces recorded that pointing an
    install at a home directory once emptied it — and then reported success.
    """


def home() -> Path:
    """The one root: everything this install keeps stands below it.

    Resolved from `RUNDESK_HOME` on every call, falling back to `~/.rundesk`.

    **Unset and set-to-empty are different answers.** Nobody having said where the install is means
    the default, and is ordinary. A variable that is *there and empty* means something tried to say
    and produced nothing — a script whose own variable was unset, a scrubber that ran in the wrong
    order — and treating that as "nobody said" points the command at the owner's live install at the
    exact moment somebody was trying to point it elsewhere. So it is refused out loud.
    """
    said = os.environ.get(HOME_IS)
    if said is None:
        return allowed(Path(DEFAULT_HOME).expanduser(), HOME_IS)
    if not said.strip():
        raise Refused(f"{HOME_IS} is set and empty, which is not the same as unset")
    return allowed(Path(said).expanduser(), HOME_IS)


def app() -> Path:
    """The program itself — what an update replaces and an uninstall takes whole.

    Kept apart from `data()` so that replacing rundesk cannot reach what the owner accumulated, and
    removing rundesk does not have to remember not to.
    """
    return home() / "app"


def data() -> Path:
    """Everything the owner accumulates: agents, logs, skills, catalogs, configuration.

    Never touched by an update, and kept by an uninstall unless a purge asks for it.
    """
    return home() / "data"


def backups() -> Path:
    """Copies of what the owner keeps, which survive removal — including a purge.

    A copy is worth nothing if the thing that takes the product away takes the copies too.
    """
    return home() / "backups"


def projects() -> Path:
    """The shared directory work is checked out into. The owner's, never rundesk's to tidy."""
    return home() / "projects"


def program() -> Path:
    """Where *this* copy of the program is running from, resolved rather than assumed.

    `.resolve()` follows the symlink an install puts on a PATH back to the tree it points at, which
    is what lets a checkout and an install share one layout. **This never answers where the data
    is** — see the module docstring.

    Found by looking upward for the tree's own marker rather than by counting directories. Counting
    is right until a module moves one level deeper, and then it is quietly wrong: this module moving
    into `core/` made a `parents[2]` report `src/` as the program, and nothing failed — `status`
    simply printed a path that was not the answer.
    """
    here = Path(__file__).resolve()
    for above in here.parents:
        if (above / "src" / "rundesk" / "__init__.py").is_file():
            return above
    raise Refused(f"could not find the rundesk tree above {here}")


def allowed(where: Path, called: str) -> Path:
    """A directory rundesk may keep things below, or `Refused` saying why it may not be one.

    Everything below such a directory is something rundesk may replace or delete, so one that is too
    broad is not a misconfiguration to work around — it is one command away from taking somebody's
    home with it. The installer this replaces recorded that pointing an install at a home directory
    once emptied it, and then reported success.

    **Shared rather than written once per caller**, because the reasoning does not change with the
    subject. The root is one such directory; so is anywhere else the owner points rundesk at, and the
    command that moves the copies somewhere would otherwise be the second command written to empty a
    home. `called` is what the caller knows the directory as, so the refusal names the thing somebody
    actually set rather than a variable they have never heard of.

    **Compared after resolving, and the resolved value is what comes back.** `pathlib` never
    normalises a `..` segment and never follows a symlink to decide `==`, so comparing the path as
    typed compares a string that is not the directory anything will actually use. This guard read
    `~/Library/..` as "not the home directory" and `/tmp/../..` as "not the root", which is both
    refusals defeated by one segment — and `uninstall --purge` removes `data/` below whatever root
    got through. That is precisely the incident `docs/layout.md` records: an install pointed at a
    home directory emptied it, and reported success.

    Handing back the resolved path rather than the typed one is the other half. A value that passed
    the check and then went on being used as typed could still resolve somewhere else afterwards, so
    every location derived below the root is derived from the canonical form.
    """
    if not where.is_absolute():
        # Asked of the value as typed, and before anything is resolved: `resolve()` makes a relative
        # path absolute against whatever directory the command happened to run in, so asking after
        # would quietly accept the exact thing this refuses.
        raise Refused(f"{called} must be an absolute path, and is {where}")

    settled = where.resolve()
    if settled == Path(settled.anchor):
        raise Refused(f"{called} must not be the root of the filesystem, and is {_both(where, settled)}")
    if settled == Path.home().resolve():
        raise Refused(f"{called} must not be the home directory itself, and is {_both(where, settled)}")
    if settled.parent == settled:
        raise Refused(f"{called} has no parent, and is {_both(where, settled)}")
    return settled


def _both(where: Path, settled: Path) -> str:
    """What was typed, and what it turned out to be when they differ.

    A refusal naming only `~/Library/..` reads as arbitrary; naming only `/Users/you` reads as a
    value nobody set. The person needs both to see why.
    """
    return str(where) if settled == where else f"{where}, which is {settled}"
