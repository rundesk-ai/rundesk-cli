"""The directories an install keeps things in, and the note standing in each one.

Every one of these is made by the install and never by the thing that uses it, so a fresh machine has
the whole shape from the first moment rather than growing it a directory at a time as features are
first used.

The notes exist because **an agent working on this machine will walk into these directories**, and a
bare empty folder tells it nothing — an agent that finds `projects/` with nothing in it has no way to
know it is the right place to check a repository out into, so it picks somewhere else. One short
`README.md` per directory answers that.

They are rundesk's own notes and are **brought forward on every install and update**, so a wording
fix reaches machines that already exist. Each says so at the top, so nobody puts their own notes in a
file that will be rewritten under them.
"""

from pathlib import Path
from typing import Callable, Dict, List, Optional

from rundesk.core import paths

_WRITTEN_BY_US = (
    "<!-- Written by rundesk, and rewritten on every install and update.\n"
    "     Your own notes belong in a file of your own, beside this one. -->\n\n"
)

DATA_NOTE = """# data/

Everything rundesk keeps for this install: agents, their homes and histories, logs, skills, and
`config.json`, which holds the install-wide settings.

**This directory is yours and rundesk protects it.** An update never touches it, and an uninstall
keeps it unless it is explicitly asked to purge. Copies of it go to `../backups/`.
"""

BACKUPS_NOTE = """# backups/

Copies of `../data/` — everything rundesk keeps for you.

**Nothing rundesk does removes a copy from here**, including an uninstall asked to purge the data.
That is the point of the directory: a copy is worth nothing if the thing that takes the product away
takes the copies with it.

This directory may be moved elsewhere and linked back to from here, so copies can live on another
disk.
"""

PROJECTS_NOTE = """# projects/

A shared, empty working directory for agents.

**If you are an agent and you need somewhere to put a repository, put it here.** Clone into
`projects/<name>/`, work in it, and leave it for the next turn — this directory is not cleaned up
between runs and is shared by every agent on this install.

Nothing in here belongs to rundesk. It is never replaced by an update, never read as configuration,
and never tidied. It is not backed up either: what is in here is expected to be a checkout of
something that lives somewhere else.
"""

AGENTS_NOTE = """# agents/

One directory per agent, named as that agent is.

Each holds `state.db` — everything that agent has ever kept — a `home/` it starts in and reads from,
and `logs/`, where its gateway says what it has been doing.

**If you are an agent, the one named after you is yours.** Every other directory here is another
agent's whole memory, and nothing rundesk does gives one agent a reason to read another's.

Made by the install rather than by the command that adds the first agent, so a fresh machine has the
shape from the first moment. An empty one means nobody has added an agent yet.
"""

#: Which note stands in which directory. The one list, read by both the making and the checking.
NOTES: Dict[str, str] = {
    "data": DATA_NOTE,
    "agents": AGENTS_NOTE,
    "backups": BACKUPS_NOTE,
    "projects": PROJECTS_NOTE,
}


def directories(root: Optional[Path] = None) -> Dict[str, Path]:
    """The directories an install keeps things in, by name.

    `app/` is deliberately absent: it is placed by `tree.place` as one whole thing rather than made
    empty and filled, and it is the one directory here that an update replaces.

    **Not all of these stand directly below the root**, and `agents` is the first that does not: it
    belongs under `data/` because it is something the owner accumulated, and what protects `data/`
    from an update has to protect it too. Derived from `where` rather than from `paths.agents()` for
    the same reason every other entry is — this function answers about a root it may be handed, and
    `paths` only ever answers about the one in the environment.
    """
    where = root or paths.home()
    return {"data": where / "data", "agents": where / "data" / "agents",
            "backups": where / "backups", "projects": where / "projects"}


def prepare(root: Optional[Path] = None,
            saying: Optional[Callable[[str], None]] = None) -> List[Path]:
    """Make every directory and bring its note up to date. Returns what was made or rewritten.

    Safe to run on an install that already has all of it — which is exactly what happens on every
    update, and is why nothing here refuses when something is already there.

    **Walked parents before children, and sorted by the path rather than by the name.** Sorting the
    names was harmless while every directory stood directly below the root and stopped being so the
    moment one did not: `agents` sorts before `data`, so a file sitting where `data/` belongs was
    reported as `Not a directory: …/data/agents` — a true sentence about the wrong path, naming a
    directory the person has nothing to fix and hiding the one they do.

    Sorted here rather than left to the order `directories` happens to list them in, because that
    order would then be load-bearing and nothing would say so: somebody tidying the mapping into
    alphabetical order would put the failure back, silently.
    """
    said = saying or (lambda _line: None)
    touched = []
    for name, where in sorted(directories(root).items(), key=lambda entry: entry[1].parts):
        if not where.is_dir():
            where.mkdir(parents=True, exist_ok=True)
            said(f"made {where}")
            touched.append(where)
        note = where / "README.md"
        wanted = _WRITTEN_BY_US + NOTES[name]
        if _reads_as(note) != wanted:
            note.write_text(wanted, encoding="utf-8")
            touched.append(note)
    return touched


def _reads_as(note: Path) -> str:
    """What the note currently says, or `""` when there is nothing readable there.

    An unreadable note is treated as absent here, and that is safe in a way it would not be for
    state: this file holds nothing anybody typed, so rewriting it loses nothing.
    """
    try:
        return note.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return ""
