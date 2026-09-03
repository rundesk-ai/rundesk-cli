"""Put a team's catalog and the agents it touched back when reconciliation does not finish.

Reconciling a team writes to places that share no transaction: the installed catalog tree, two
instruction pages and a memory page for each member, three columns of each member's records, and a
directory of grants. Every one of those writes is already whole-or-absent on its own. **Nothing
made them whole together**, so a failure part-way through the member loop left some agents governed
by the new catalog version and some by the old, underneath a catalog that had already moved — and
the next turn admitted read whichever half it found.

**A compensating restore, not a transaction.** What can be put back is what was read before the
change began, and a failure while putting something back is reported through `Refused` rather than
swallowed, so the outcome is never a success nobody earned.

**An agent this operation created is taken away again.** It was tempting to leave one standing on
the grounds that the team lifecycle deletes no agent, and that was wrong: the rule protects an
agent somebody *has*, and one this failed update made a minute ago is not that — leaving it behind
is this operation's own litter, standing in a name the next attempt then finds occupied. What the
rule does still forbid is exactly what this does not do: nothing that existed before the block
began is ever removed. See `docs/requirements/team-catalog.md`.
"""

import contextlib
import os
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, NamedTuple, Optional, Set

from rundesk.agents import directory, records
from rundesk.skills import grants, library
from rundesk.utils import files

#: The pages team reconciliation replaces or removes, and therefore the ones held.
PAGES = ("AGENTS.md", "CLAUDE.md", "MEMORY.md")

#: The record columns team reconciliation writes, and therefore the only ones put back. Restoring a
#: column this operation never touched would undo whatever else changed it while the update ran.
COLUMNS = ("describes", "delegates_to", "self_improve")

TROUBLE = (directory.Refused, records.NotThere, records.Unreadable, records.Refused,
           library.Refused, grants.Refused, grants.NotPresented, grants.HalfCopied, OSError)


class Refused(Exception):
    """What this operation changed could not be put back, named with what is where."""


class _Page(NamedTuple):
    """One page as it stood: the bytes it held, the link it was, or neither when it was not there.

    Three states rather than two, because reconciliation replaces a symlinked page with a file of
    its own and `files.remove_one` takes a link away as a link. Recorded as bytes-or-nothing, a
    page somebody had linked elsewhere came back as no page at all — the restore deleted the link
    it was supposed to be putting back.

    **Three, and nothing else is represented at all.** A directory or a device standing where a page
    belongs is refused while snapshotting rather than recorded as absent, because "absent" is put
    back by removing whatever is there, and `files.remove_one` removes a directory with everything
    inside it. See `_read`.
    """

    was: Optional[bytes]
    link: Optional[str]


class _Agent(NamedTuple):
    """One agent's durable state as it stood before reconciliation began."""

    name: str
    pages: Dict[str, _Page]
    settled: Dict[str, Any]
    holding: Dict[str, str]


@contextlib.contextmanager
def kept(catalog: str, members: List[str]) -> Iterator[None]:
    """Hold this catalog and every agent it can reach, putting all of it back if the block raises.

    **The caller holds the install lock**, which is what makes reading the state and changing it two
    halves of one decision rather than a race of their own.

    **Held from before the catalog arrives, so a confirmed install is covered too.** There may be
    no catalog here yet, and there may be no members yet; both are states this holds rather than
    things it requires. What it does not undo is a dependency catalog installed before the block
    was entered — see `docs/requirements/team-catalog.md`.

    `members` are the names the incoming declaration governs, and they are the only agents whose
    pages and records this holds — those are what reconciliation writes. Every other agent holding
    a grant from this catalog is held for its grants alone, because retiring a skill reaches an
    agent no team declares and nothing else about one is this operation's to put back. A declared
    name that is not an agent yet is held as a name rather than as state: there is nothing of it to
    put back, and what the restore owes is that it is not there afterwards either.
    """
    at = library.stands(catalog)
    aside = files.outgoing_of(at)
    files.discard(aside)
    # Whether there was a catalog here at all. A confirmed install enters this with nothing
    # standing, and "put it back" then means take away what the install put there — the same
    # absent-is-a-state distinction `_Page` makes about a page.
    stood = at.is_dir()
    try:
        # **Inside the guard, not before it**, the way `catalogs._swapped` holds its own copy: a
        # copytree that fails partway would otherwise leave the held tree behind with nothing to
        # tidy it, because the `finally` that discards it had not been entered yet.
        if stood:
            shutil.copytree(at, aside, symlinks=True)
        known = set(directory.known())
        declared = [name for name in members if name in known]
        settled = ([_read(name) for name in declared]
                   + [_grants_only(name) for name in _also_holding(catalog, known, declared)])
        made = [name for name in members if name not in known]
        try:
            yield
        except BaseException as why:
            trouble = _put_back(at, aside, stood, settled, made)
            if trouble:
                raise Refused(f"{why}; and what it had already changed could not be put back: "
                              f"{trouble}") from why
            raise
    finally:
        files.discard(aside)


def _also_holding(catalog: str, known: Set[str], declared: List[str]) -> List[str]:
    """Every other existing agent holding a grant from this catalog, in name order."""
    address = f"{catalog}/"
    return [name for name in sorted(known - set(declared))
            if any(held.address.startswith(address) for held in grants.held(name))]


def page_trouble(name: str) -> str:
    """Why this member's managed pages could not be put back, or `""` when they could.

    **Asked by `reconcile.preflight_update` for every declared member that already exists**, so a
    page nothing here could restore refuses the team while its gateway is still up, its catalog is
    still the one that works, and no dependency has been fetched. `_read` asks the same rule again
    under the install lock, and that second answer is the one the restore actually relies on — the
    only thing holding these paths still between the two is the lock.

    Asked of declared members alone. An agent this catalog merely reaches through a grant has pages
    that nothing here reads or writes, and refusing a whole team over the shape of one would be
    this operation taking an interest in state it does not own.
    """
    for page in PAGES:
        trouble = _page_trouble(directory.home(name) / page)
        if trouble:
            return trouble
    return ""


def _page_trouble(one: Path) -> str:
    """Why `one` could not be put back if a restore had to, or `""` when it could.

    Anything at one of these three paths that is not a file and not a link — a directory somebody
    keeps notes in, a fifo, a device — has no representation in `_Page`, so it would be held as
    absent and *restored* by removing it, and `files.remove_one` removes a directory whole.
    Refusing costs one team an update it can have back by moving the directory; the alternative
    silently deleted owner data while reporting that it had put everything back.

    `lexists`, not `exists`: the question is what stands at this name, not what it leads to. A
    broken link is still a link and is put back as the same broken link.
    """
    if one.is_symlink() or one.is_file() or not os.path.lexists(one):
        return ""
    return (f"{one} is neither a file nor a link, so a team update could not put it back if it had "
            f"to undo itself — move it aside and retry")


def _page_read(one: Path) -> _Page:
    """One page as it stands, refusing whatever `_page_trouble` says could not be put back.

    Asked as a link before a file, because `is_file` follows one: a page linked at a real file
    would otherwise be recorded as bytes and put back as a file of rundesk's own.
    """
    trouble = _page_trouble(one)
    if trouble:
        raise Refused(trouble)
    if one.is_symlink():
        return _Page(None, os.readlink(one))
    if one.is_file():
        return _Page(one.read_bytes(), None)
    return _Page(None, None)


def _read(name: str) -> _Agent:
    """A declared member's pages, reconciled record columns, and grants, as they stand."""
    home = directory.home(name)
    pages = {page: _page_read(home / page) for page in PAGES}
    try:
        row = records.read(directory.records(name))
        settled = {column: row[column] for column in COLUMNS if column in row}
    except (records.NotThere, records.Unreadable):
        # Nothing to put back rather than a refusal: an agent whose records will not open is
        # already refused before any of this runs, and holding the pages and grants of one that
        # somehow reached here is still better than holding none of it.
        settled = {}
    return _Agent(name, pages, settled, _holding(name))


def _grants_only(name: str) -> _Agent:
    """An agent this catalog reaches only through a grant: its grants, and nothing else of it.

    Retiring a skill revokes it wherever it stands, so a holder no team declares has to be put
    back. **Its pages and records are not this lifecycle's to hold.** Reconciliation never writes
    them, so a snapshot of them is a restore standing ready to overwrite whatever else changed them
    while the update ran — and reading them at all would let one irrelevant page shape refuse a
    whole team. Held as an `_Agent` with nothing in the two fields it does not own, so
    `_agent_put_back` needs no second shape to know what it may touch.
    """
    return _Agent(name, {}, {}, _holding(name))


def _holding(name: str) -> Dict[str, str]:
    """Every grant standing in this agent's directory, by the name it is held under."""
    return {one.name: one.address for one in grants.held(name)}


def _put_back(at: Path, aside: Path, stood: bool, settled: List[_Agent],
              made: List[str]) -> str:
    """Put the catalog back, then every agent, then take away the agents this made. Returns
    what would not go, or an empty string.

    **The catalog first.** A grant is put back by looking its skill up in the catalog it came from,
    so the tree that holds it has to be standing again before any of them are asked for.

    **What it created last**, so a name that is both declared and reachable is restored as the agent
    it was before it is judged new — it never is, but the order costs nothing and the alternative
    depends on that.
    """
    trouble: List[str] = []
    try:
        _catalog_put_back(at, aside, stood)
    except OSError as why:
        trouble.append(f"the catalog at {at} could not be put back ({why})")
    for one in settled:
        trouble.extend(_agent_put_back(one))
    for name in made:
        trouble.extend(_agent_taken_away(name))
    return "; ".join(trouble)


def _agent_taken_away(name: str) -> List[str]:
    """Take away an agent this reconciliation created. Returns what would not go.

    **Removed without asking whether a gateway is running**, which `directory.forgotten` leaves to
    its caller for a layering reason and which this caller can answer from what it knows: the name
    was not an agent when the block began, only a confirmed team command creates a member, and that
    command starts no gateway — so there is nothing running that this could pull out from under.

    Asked of the directory rather than of `directory.known`, because a creation that did not finish
    leaves one without records and that is exactly the half this has to take away.
    """
    if not directory.where(name).is_dir():
        return []
    try:
        directory.forgotten(name)
    except TROUBLE as why:
        return [f"{name}, which this update created, could not be taken away ({why})"]
    return []


def _catalog_put_back(at: Path, aside: Path, stood: bool) -> None:
    """Swap the held copy back into place, one rename wide, the way it was replaced.

    **Nothing standing here before means taking away what arrived**, which is what a confirmed
    install has to undo. Renamed aside rather than removed where it stands, the way
    `catalogs.remove` does it and for its reason: an `rmtree` that fails halfway leaves a
    directory that is still a catalog by every test — it has a manifest — and is missing an
    arbitrary half of its skills. The rename is the moment it stops being one, and `kept` discards
    the renamed copy either way.
    """
    if not stood:
        if at.exists():
            files.discard(aside)
            os.rename(at, aside)
        return
    if not aside.is_dir():
        return
    gone = files.incoming_of(at)
    files.discard(gone)
    moved = False
    if at.exists():
        os.rename(at, gone)
        moved = True
    try:
        os.rename(aside, at)
    except OSError:
        if moved and not at.exists():
            os.rename(gone, at)
        raise
    files.discard(gone)


def _agent_put_back(one: _Agent) -> List[str]:
    """Put one agent's pages, record columns, and grants back. Returns what would not go."""
    trouble: List[str] = []
    home = directory.home(one.name)
    for page, was in one.pages.items():
        try:
            _page_put_back(home / page, was)
        except OSError as why:
            trouble.append(f"{one.name}'s {page} could not be put back ({why})")
    if one.settled:
        try:
            records.stated(directory.records(one.name), dict(one.settled))
        except TROUBLE as why:
            trouble.append(f"{one.name}'s description, delegation and upkeep could not be put "
                           f"back ({why})")
    trouble.extend(_grants_put_back(one))
    return trouble


def _page_put_back(at: Path, was: _Page) -> None:
    """Restore one page's bytes, the link it was, or its absence.

    Staged and renamed for the reason `agents.pages` stages: a provider may read this directory at
    any moment, and half a restored `AGENTS.md` is a smaller set of rules rather than a failure. A
    link is staged the same way and renamed as a link, never followed — writing through one would
    put this team's instructions into whatever the owner had pointed at.
    """
    if was.link is not None:
        if at.is_symlink() and os.readlink(at) == was.link:
            return
        _staged(at, lambda staging: os.symlink(was.link, staging))
        return
    if was.was is None:
        files.remove_one(at)
        return
    if at.is_file() and not at.is_symlink() and at.read_bytes() == was.was:
        return
    _staged(at, lambda staging: staging.write_bytes(was.was))


def _staged(at: Path, write: Callable[[Path], Any]) -> None:
    """Build the replacement for `at` beside it and move it into place, or leave nothing behind."""
    staging = files.incoming_of(at)
    files.discard(staging)
    try:
        write(staging)
        os.replace(staging, at)
    except BaseException:
        files.discard(staging)
        raise


def _grants_put_back(one: _Agent) -> List[str]:
    """Take away every grant that is not what stood there, and give back every one that was."""
    trouble: List[str] = []
    standing = {held.name: held.address for held in grants.held(one.name)}
    for name, address in sorted(standing.items()):
        if one.holding.get(name) == address:
            continue
        try:
            grants.revoked(one.name, name)
        except TROUBLE as why:
            trouble.append(f"{one.name}'s {address or name} grant could not be taken back ({why})")
    for name, address in sorted(one.holding.items()):
        if standing.get(name) == address:
            continue
        try:
            skill = library.look_up(address)
            grants.granted(one.name, skill, "" if name == skill.name else name)
        except TROUBLE as why:
            trouble.append(f"{one.name}'s {address} grant could not be put back ({why})")
    return trouble
