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
        return _allowed(Path(DEFAULT_HOME).expanduser())
    if not said.strip():
        raise Refused(f"{HOME_IS} is set and empty, which is not the same as unset")
    return _allowed(Path(said).expanduser())


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


def _allowed(root: Path) -> Path:
    """The root, or `Refused` saying why it may not be one.

    Everything below is a directory an uninstall may delete, so a root that is too broad is not a
    misconfiguration to work around — it is one command away from taking somebody's home with it.
    """
    if not root.is_absolute():
        raise Refused(f"{HOME_IS} must be an absolute path, and is {root}")
    if root == Path(root.anchor):
        raise Refused(f"{HOME_IS} must not be the root of the filesystem, and is {root}")
    if root == Path.home():
        raise Refused(f"{HOME_IS} must not be the home directory itself, and is {root}")
    if root.parent == root:
        raise Refused(f"{HOME_IS} has no parent, and is {root}")
    return root
