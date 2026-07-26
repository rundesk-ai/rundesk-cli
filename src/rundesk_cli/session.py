"""Where a conversation got to, so the next turn carries on from it.

A brain's own handle for a conversation it can pick back up. Opaque here and never
interpreted (R-RUN-13): whatever it means is that brain's business, and reading it would
be a vendor concept in the core wearing a string's clothes.

**Kept for a conversation and a brain together, never for either alone (R-RUN-12).** The
brain is the outer key, so the pairing is the shape of the file rather than a rule
somebody has to remember — losing the brain from the key is not a mistake that can be
made here, because there is nowhere to write a handle that is not already inside one
brain's own book. The build this replaces keyed on the conversation alone, which hands one
brain's session to the next the moment an agent's provider changes.

**Losing it costs the next turn its context and nothing else (R-RUN-14).** That is the
whole reason it is a small file rather than anything larger: an unreadable book is a
conversation that starts fresh, which is a bad turn, and refusing to start is a dead
agent.
"""

from __future__ import annotations

import json
from pathlib import Path

from rundesk_cli import gateway

#: What the book is called, beside everything else that is one agent's own. Not inside a
#: provider's private home, which is the adapter's to write in — a brain must not be able
#: to reach the record of which conversations it is holding for us.
BOOK = "sessions.json"


def book(directory: Path) -> Path:
    """Where this agent's handles are kept."""
    return directory / BOOK


def of(directory: Path, provider: str, conversation: str) -> str | None:
    """What this brain last reported for this conversation, or nothing.

    Nothing is the ordinary answer: a conversation that has not run yet, a brain that
    cannot carry one on, and a book that was lost all mean the same thing to the caller —
    start fresh.
    """
    return _read(book(directory)).get(provider, {}).get(conversation) or None


def remember(directory: Path, provider: str, conversation: str, handle: str) -> bool:
    """Keep where this conversation got to, under this brain and no other.

    Read, decided and written under one hold, because two turns finishing together each
    write the whole book back and the later one would erase the other's conversation with
    both reporting success.

    Says whether it was kept. A book that cannot be read is left exactly as it stands —
    an unreadable one is not an empty one, and writing an empty one over it would throw
    away every other conversation to save this one. The cost is that the next turn on
    this conversation starts fresh, which is what losing it is supposed to cost
    (R-RUN-14), and the caller writes that into the run's account rather than nobody
    hearing about it.
    """
    if not handle:
        return False  # a brain that reported no handle has nothing to keep
    try:
        with gateway.changing(book(directory), {}, "the handles of conversations") as kept:
            held = kept.get(provider)
            if not isinstance(held, dict):
                held = {}
                kept[provider] = held
            held[conversation] = handle
    except (gateway.Unreadable, OSError):
        return False
    return True


def forget(directory: Path, provider: str, conversation: str) -> None:
    """Start this conversation fresh next time, leaving every other one alone."""
    try:
        with gateway.changing(book(directory), {}, "the handles of conversations") as kept:
            held = kept.get(provider)
            if isinstance(held, dict):
                held.pop(conversation, None)
                if not held:
                    kept.pop(provider, None)
    except (gateway.Unreadable, OSError):
        pass  # nothing is being carried on from a book nobody can read anyway


def _read(at: Path) -> dict:
    """The book, or an empty one — a book that cannot be read is a turn without context.

    Read rather than changed, so nothing here writes an empty book over one that was
    merely unreadable. What is unreadable stays on disk exactly as it is, for a person to
    look at, and the turn goes on without it.
    """
    try:
        said = json.loads(at.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(said, dict):
        return {}
    return {brain: held for brain, held in said.items() if isinstance(held, dict)}


def brains(directory: Path) -> list[str]:
    """Every brain this agent has kept a conversation under.

    Forgetting is aimed at a conversation rather than at a brain, and an agent whose
    provider changed has conversations under both — so leaving one behind would mean the
    next message carrying on from a session somebody just asked to throw away.
    """
    return sorted(_read(book(directory)))
