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
from typing import Optional

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


def agents() -> Path:
    """Where the agents this install keeps stand, one directory each.

    Below `data()` because an agent is something the owner accumulated: an update never touches it,
    and an uninstall keeps it unless a purge asks for it.

    **Derived, and there is no variable that reaches it.** The build this replaces had
    `RUNDESK_AGENTS_DIR`, and its own value beat the one for the data directory — so a scratch run
    that redirected the root, the run directory, the log directory and the jobs directory, which
    looks exhaustive, went on making agents in the owner's live install and reporting success. Three
    were created that way and had to be removed by hand. Here there is nothing to miss.
    """
    return data() / "agents"


def skills() -> Path:
    """The skill library: one directory per catalog, and the skills inside each.

    Below `data()` for the same reason `agents()` is — it is something the owner accumulated, so an
    update never touches it and an uninstall keeps it unless a purge asks for it. It follows that a
    copy of `data/` carries the whole library, which is what makes a skill an owner wrote survivable.

    **Derived, and there is no variable that reaches it.** The build this replaces had
    `RUNDESK_SKILL_LIBRARY`, one of a dozen independent locations, and a scratch run that redirected
    the others deleted an owner's installed skills while reporting an ordinary success. Here there is
    nothing to miss.
    """
    return data() / "skills"


def backups() -> Path:
    """Copies of what the owner keeps, which survive removal — including a purge.

    A copy is worth nothing if the thing that takes the product away takes the copies too.
    """
    return home() / "backups"


def secrets() -> Path:
    """Where values only this machine's owner may read are kept.

    **Deliberately not below `data/`, and that is the whole of its security.** A copy is a copy of
    `data/` and nothing else, so an install's backups are *structurally incapable* of holding a
    credential rather than careful not to — there is no code path to get one wrong, because there
    is no code that reaches here from there. The build this replaces made the same choice and said
    so in the same words.

    It follows that a credential is **not** carried by a restore either. That is the right way
    round: a value somebody typed once is not state a copy should be able to put back.
    """
    return home() / "secrets"


def projects() -> Path:
    """The shared directory work is checked out into. The owner's, never rundesk's to tidy."""
    return home() / "projects"


def lock(root: Optional[Path] = None) -> Path:
    """The file one process at a time holds while it changes an install.

    **`root` is which install, and it is not optional in spirit.** A caller handed an explicit
    directory to work on must derive the lock from *that* root, not from wherever `RUNDESK_HOME`
    happens to point — otherwise a function given somewhere to work reaches outside it to take a
    lock, and the install it touches is the default one. That is the defect this whole rebuild
    exists to have removed, in its smallest form: everything redirected but one thing, and the one
    thing resolving to the owner's live install. It really happened here, and left a lock file in
    a real install that nothing else in that run went near.

    Below the root and beside the directories rather than inside `data/`, because the operations it
    serialises *move `data/` itself* — a lock inside the thing being renamed away is a lock two
    processes can end up holding different copies of.

    One lock for the whole install rather than one per directory. The races worth stopping are
    between different commands touching different things — a restore swapping `data/` while a
    configure writes into it — and a lock per directory is a lock that lets exactly those through.
    """
    return (root or home()) / ".rundesk.lock"


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
    if _the_same_place(settled, Path(settled.anchor)):
        raise Refused(f"{called} must not be the root of the filesystem, and is {_both(where, settled)}")
    if _the_same_place(settled, Path.home()):
        raise Refused(f"{called} must not be the home directory itself, and is {_both(where, settled)}")
    if settled.parent == settled:
        raise Refused(f"{called} has no parent, and is {_both(where, settled)}")
    return settled


def _the_same_place(one: Path, other: Path) -> bool:
    """Whether two paths are the same directory — asked of the filesystem, not of the text.

    **Comparing the strings is not enough on a Mac.** The default volume is case-insensitive, and
    `resolve()` does not case-fold: `/uSERS/NAME` and `/Users/name` are one directory and two
    different strings, so a home directory spelled with different capitals sailed past the refusal
    that exists to stop exactly that — and `uninstall --purge` below such a root would have been
    operating on somebody's home for real. Not an adversarial input either: a path copy-pasted from
    a tool that does not preserve case is all it takes.

    `samefile` compares device and inode, which is the only question actually being asked. It needs
    both paths to exist, so the string comparison stays as the answer for a root that is not there
    yet — a directory that does not exist cannot be the home directory.
    """
    if one == other:
        return True
    try:
        return os.path.samefile(str(one), str(other))
    except OSError:
        return False


def _both(where: Path, settled: Path) -> str:
    """What was typed, and what it turned out to be when they differ.

    A refusal naming only `~/Library/..` reads as arbitrary; naming only `/Users/you` reads as a
    value nobody set. The person needs both to see why.
    """
    return str(where) if settled == where else f"{where}, which is {settled}"
