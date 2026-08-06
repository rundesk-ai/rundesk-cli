"""The pages an agent is given to live by, and how they get into its home.

An agent's identity is **files in a directory it stands in**, not a column in a database. Every
measured brain reads them by being in the directory, so what makes an agent behave like one is that
the files are really there — and until this module existed they were not. Every turn told a brain
its own files were in its home and set `RUNDESK_CONTINUITY` naming them; nothing had ever written
one.

## What is placed, and under what name

**A template is named for the file it becomes.** `src/templates/AGENTS.md` is what an agent's
`AGENTS.md` is copied from, so somebody reading that directory is reading exactly what a new agent
gets, with no indirection to hold in their head.

| In the home | Copied from | Is |
|---|---|---|
| `AGENTS.md` | `AGENTS.md` | how this agent works |
| `CLAUDE.md` | `AGENTS.md` | the same bytes, under the name some brains look for first |
| `MEMORY.md` | `MEMORY.md` | the scaffold it writes what it learns into |

**`AGENTS.md` and `CLAUDE.md` are one source placed twice, and identical by construction.** Two
files kept in step by anybody remembering is two files that disagree, and the disagreement is
invisible: each brain reads only the one it looks for, so the two would drift into two different
agents wearing one name. `tests/test_agent_pages.py` compares the bytes rather than trusting this
sentence.

## Absence is filled; an answer is never replaced

**A page that is already there is left exactly as it is, whatever it says.** These are the files an
agent and its owner edit — the rules say so in as many words — so a release that rewrote them would
be a release that silently changed how somebody's agent works, and the owner would find out by its
behaviour rather than by being told.

That is `skills.grants` behaviour and deliberately not `lifecycle.home`'s: an install's `README.md`
is rewritten every update because it holds nothing anybody typed, and these hold nothing else.

The cost is that an improvement to a shipped page never reaches an agent that already has it. That
is the right way round — an agent whose rules changed under it is worse than one on last release's
wording — and it is why `rundesk agents` reports which pages an agent is missing rather than
leaving it to be discovered.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from rundesk.core import paths

#: Where this release keeps them. **Answered on every call and never bound at import**: on a machine
#: with a real install `~/.rundesk/app/src` exists, and a constant resolved at import time would
#: answer out of the owner's live install before any test had set `RUNDESK_HOME`. The same rule
#: `skills.catalogs.shipped` is written to, for the same reason it is written there.
SHIPPED_IN = "templates"

#: What lands in a home, and which shipped page it comes from. **A table rather than a directory
#: walk**, because the doubling is the decision: `AGENTS.md` is placed twice, and a walk that put
#: each shipped page down under its own name could not say so without a second copy on disk that
#: somebody would have to keep identical by hand.
PAGES: Dict[str, str] = {
    "AGENTS.md": "AGENTS.md",
    "CLAUDE.md": "AGENTS.md",
    "MEMORY.md": "MEMORY.md",
}

#: The one thing a page substitutes on the way in. Doubled braces, so it cannot collide with the
#: single-brace names `providers.instructions` fills — a page is written by hand and a brace in it
#: must be able to mean a brace.
AGENT = "{{agent}}"


class Missing(Exception):
    """This release ships no pages, so there is nothing to give an agent.

    Its own kind because it is a broken *checkout or release*, not a broken agent: every other
    failure here is about one home, and a caller that reported them the same way would send somebody
    looking at an agent when the fault is in the tree the code was run from.
    """


def shipped() -> Path:
    """Where this release's own pages stand. Resolved on every call — see `SHIPPED_IN`."""
    return paths.code() / SHIPPED_IN


def sources() -> List[str]:
    """Every shipped file a page is copied from, named once however many pages use it."""
    return sorted(set(PAGES.values()))


def read_shipped() -> Dict[str, str]:
    """The text of every page this release would place, read once.

    **Read together and up front**, so a home is never left holding two of three pages because the
    third could not be read. Anything that stops one from being read stops all of them, before a
    single file has been written.
    """
    at = shipped()
    said = {}
    for name in sources():
        page = at / name
        try:
            said[name] = page.read_text(encoding="utf-8")
        except OSError as why:
            raise Missing(f"this release ships no {name} at {at} ({why})") from why
    if not said:
        raise Missing(f"this release ships no pages at all at {at}")
    return said


def wanted(home: Path) -> List[str]:
    """Which pages are not in this home. Empty means it has them all.

    An unreadable entry is **not** a missing one. A file somebody made unreadable is still an answer
    standing there, and writing over it because it could not be read is exactly the "missing and
    unreadable are different" failure this product is built to refuse.

    **Asked with `lexists`, so a link is judged as itself and never as what it points at.** An owner
    who linked `AGENTS.md` at a file they keep somewhere else has answered where their rules live,
    and `exists()` calls that link missing for as long as the far end is unreachable — an unmounted
    volume, a checkout not cloned yet. The sweep would then land a regular file on top of it and the
    link would be gone for good, because the replacement is what every later run finds.
    """
    return [name for name in sorted(PAGES) if not _stands(home / name)]


def _stands(page: Path) -> bool:
    """Whether anything at all is at this name — a file, a directory, or a link of any health."""
    return page.exists() or page.is_symlink()


def place(home: Path, agent: str, text: Optional[Dict[str, str]] = None) -> List[str]:
    """Put every page this home is missing into it. Hands back what was written, in order.

    **Fills an absence and never replaces an answer** — see the module docstring. A page already
    standing is skipped without being read, so nothing here can be fooled by what it says.

    `text` is what `read_shipped` gave, passed in when a caller is placing for many agents so the
    release's own files are read once rather than once per agent. Resolved in the body when it is
    not — never in the signature, where it would be bound at import and unreachable by a test.
    """
    said = read_shipped() if text is None else text
    written = []
    for name in sorted(PAGES):
        page = home / name
        if _stands(page):
            continue
        _laid_down(page, said[PAGES[name]].replace(AGENT, agent))
        written.append(name)
    return written


def _laid_down(page: Path, text: str) -> None:
    """Write one page so that it is whole or is not there.

    Staged beside itself and renamed, because a home is somewhere a brain reads at any moment: an
    agent whose gateway is up can be part-way through a turn while an update is filling in a page,
    and a partially written `AGENTS.md` is a set of rules with the end missing — which reads as a
    complete smaller set rather than as a failure.
    """
    staging = page.with_name(f".{page.name}.incoming")
    try:
        staging.write_text(text, encoding="utf-8")
        os.replace(staging, page)
    except BaseException:
        try:
            staging.unlink()
        except OSError:
            pass
        raise


def everybody_has_theirs(names, home_of, saying=None) -> List[Tuple[str, str]]:
    """Give every agent the pages it is missing. Hands back what could not be done, per agent.

    **Never raises for one agent's sake.** This runs inside `update`'s settle, where the install has
    already been carried forward — one home that cannot be written is one agent to name, and taking
    the whole update down with it would leave every other agent uncarried for the sake of the one.

    `names` and `home_of` are handed in rather than reached for, because `agents` may not import the
    layer that knows how a command finds them, and a sweep that resolved its own work could not be
    driven by a case with no install anywhere near it.

    A release that ships no pages at all is the one failure that is not per-agent: it is reported
    once and nothing is attempted, rather than as the same sentence repeated for every agent.
    """
    told = saying or (lambda _line: None)
    try:
        text = read_shipped()
    except Missing as why:
        told(str(why))
        return []
    left = []
    for name in names:
        try:
            written = place(home_of(name), name, text)
        except OSError as why:
            left.append((name, str(why)))
            told(f"{name} is missing pages that could not be written ({why})")
            continue
        if written:
            told(f"{name} was given {', '.join(written)}")
    return left
