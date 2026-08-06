"""The program behind a provider: finding it, asking what it can do, and starting one for a turn.

The mirror of `channels.adapters`, and deliberately the same shape. Finding a program, what it is
started with, and reading what one printed are the same questions for both kinds, so they live in
`core.adapters`; what is here is only what is a *provider's*.

Two questions are asked of one, and they are not alike.

**`--capabilities`** is asked offline: no account, no network, the same answer every time. It is what
lets an absence be a fact rather than a guess — a turn that reported no tools is told apart from a
brain that has none, which is a distinction nothing can recover afterwards. Absent means no, so an
adapter answering `{}` is a complete and honest one, and that is what makes a plain conversational
CLI first class rather than degraded.

**Starting one** is not a question at all. It is a program that will run for as long as the turn
does, which may be hours, and everything about reading it is `providers.streaming`'s.

**There is no `--check`.** A channel adapter has one because it signs in to somebody else's service
and an owner has to find out at a terminal rather than at three in the morning. A provider adapter
has nothing to check offline: whether a brain is signed in is a question with an answer that changes
between one turn and the next, and asking it before every turn would double what every turn costs.
A brain that is not signed in says so, and the seam has a word for it — see `protocol.SIGNED_OUT`.

## Where an install's own adapters go

`data/providers/`, and **not** the `data/adapters/` a channel's own go in. The two kinds do not share
a namespace: a channel called `discord` and a provider called `discord` are different programs, and
one directory holding both would make them one file.

May depend on `channels`, `agents`, `core` and `utils`. Nothing here names a vendor.
"""

import hashlib
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from rundesk.agents import directory
from rundesk.core import adapters
from rundesk.providers import streaming
from rundesk.utils import logs, programs

#: Where the provider adapters that ship stand, under whatever `paths.code()` resolves to, and where
#: the ones an install has been given stand. Two places and no third: one is part of the release and
#: is replaced by an update, the other is the owner's and is never touched by one.
SHIPPED_IN = "providers"
GIVEN_IN = "providers"

#: How long `--capabilities` may take. It is a question whose answer the adapter already knows, asked
#: with no network and no account — and the ceiling exists because **this is the one place rundesk
#: runs an unvetted program before a turn has been admitted**. Without it, an adapter that is chatty
#: or broken hangs every ask with nothing written down anywhere.
CAPABILITIES_WITHIN = 60.0

#: What a provider's own directory is called inside an agent's tree. One per (agent, provider), and
#: **named to the adapter, never made by rundesk**: pointed at a directory that exists, a real brain
#: does not merely keep a sign-in there — it builds its whole state tree, to tens of megabytes an
#: agent. What the adapter does inside it is the adapter's business.
PROVIDERS = "providers"

#: Where a turn's own things stand inside an agent's tree, one directory per conversation. Named here
#: because `errors_of` is what hands the path to a running adapter, and a second place naming it is a
#: second thing to keep in step.
CONVERSATIONS = "conversations"

#: What a conversation's directory holds. The lock is the claim on it — one turn at a time — and the
#: two files are appended across turns and rotated, rather than written one per turn: an agent taking
#: fifty turns a day would otherwise leave seventy-odd thousand files a year.
LOCK = "lock"
RAW = "raw.jsonl"
ERRORS = "stderr.log"

#: When a conversation's two files are worth moving aside, and how many previous ones are kept. The
#: same shape `channels.hosting` rotates an adapter's error log with, and for the same reason.
KEPT_OVER = 256 * 1024
KEPT_BACK = 3

NotRunnable = adapters.NotRunnable


def where(named: str) -> Path:
    """The program behind this provider. See `core.adapters.where`.

    A bare name resolves among the ones that ship and then among the ones this install has been
    given; anything with a separator is used as a path. **Not recognising a name is not a failure** —
    a brain rundesk has never heard of is the ordinary case this seam exists for.
    """
    return adapters.where(named, SHIPPED_IN, GIVEN_IN)


def known() -> List[str]:
    """Every provider adapter this install can run, in name order, found by looking."""
    return adapters.known(SHIPPED_IN, GIVEN_IN)


def key(named: str) -> str:
    """One filesystem-safe name for this provider, for the directory kept per brain.

    A shipped name is its own. A path becomes its last part with a little of the whole path after it,
    because **two adapters called `brain` in two directories are two brains** — giving them one
    private home would hand one's credentials and session files to the other.

    Short and stable rather than pretty: it names a directory, and the name an owner reads is the one
    they typed.
    """
    if not _is_a_path(named):
        return _plainly(named) or "brain"
    stands = Path(named).expanduser()
    marked = hashlib.sha256(str(stands).encode("utf-8")).hexdigest()[:8]
    return f"{_plainly(stands.name) or 'brain'}-{marked}"


def home(agent: str, named: str) -> Path:
    """Where this (agent, provider) keeps whatever it keeps between turns.

    **Named to the adapter and never made here.** See `PROVIDERS`: a real brain pointed at a
    directory builds its whole state tree in it, and whether it should is the adapter's decision and
    not rundesk's.
    """
    return directory.where(agent) / PROVIDERS / key(named)


def conversation_at(agent: str, conversation: int) -> Path:
    """The directory one exchange keeps its claim and its two appended files in."""
    return directory.where(agent) / CONVERSATIONS / str(conversation)


def lock_of(agent: str, conversation: int) -> Path:
    """The file the kernel holds while a turn is running in this conversation."""
    return conversation_at(agent, conversation) / LOCK


def raw_of(agent: str, conversation: int) -> Path:
    """Everything the *brain* said, verbatim, appended across every turn of this conversation.

    Handed to the adapter as `RUNDESK_RAW` and written by it, never by rundesk. Without it, rundesk
    sees what the *adapter* reported and never what the brain said — so a vendor changing its output
    shape shows up as records quietly going missing, with nothing to compare against.
    """
    return conversation_at(agent, conversation) / RAW


def errors_of(agent: str, conversation: int) -> Path:
    """Everything the adapter said went wrong, appended across every turn of this conversation.

    A file rather than rows, and deliberately: this is an operating-system pipe, and it may be
    destroyed to reclaim space **without the account losing anything**. That is only true because
    nothing a turn recorded is recoverable only from here.
    """
    return conversation_at(agent, conversation) / ERRORS


def capabilities(named: str,
                 running: Optional[Callable[..., programs.Ran]] = None) -> Dict[str, Any]:
    """What this brain says it can do. `{}` when it would not say, which is a whole answer.

    **Asked rather than assumed, and never guessed from a name.** An adapter that does not recognise
    the flag and does something else can do nothing, which is complete and honest and not an error —
    so every failure here is an empty mapping rather than an exception.

    Whatever else the answer carries is kept as it stands. An adapter reporting its own brain's
    version is answering a question rundesk did not ask, and it is exactly what somebody reads a
    month later to find out what changed — so it is written into the turn verbatim rather than
    parsed, which would be this side inventing a schema for a field it does not own.

    Resolved inside the body rather than bound in the signature: a default bound at definition is
    decided once, when the module is imported, and nothing can reach past it.
    """
    ran = (running or programs.run)([str(where(named)), "--capabilities"],
                                    CAPABILITIES_WITHIN, env=adapters.environment())
    if ran.trouble or ran.code != 0:
        return {}
    said = adapters.printed_object(ran.out)
    return said if isinstance(said, dict) else {}


def talking_to(named: str, env: Dict[str, str], agent: str, conversation: int,
               holding: int) -> streaming.Stream:
    """Start this brain for one turn, and hand back the stream it is read on.

    **Unbounded, unlike `capabilities`.** A turn may legitimately run for hours; what bounds it is
    silence and a far-off ceiling, and both are `providers.streaming`'s.

    `holding` is the conversation's claim, passed down so the kernel holds it for exactly as long as
    the adapter and everything it started are alive — **however this process dies, including
    `SIGKILL`**. That is what makes a turn's liveness a question for the kernel rather than for a
    written-down process id that gets reused.

    The error log is rotated on the way in rather than on the way out: a turn that was killed wrote
    just as much as one that was not, and only the next turn is in a position to tidy up after it.
    """
    errors = errors_of(agent, conversation)
    errors.parent.mkdir(parents=True, exist_ok=True)
    logs.rotated(errors, KEPT_OVER, KEPT_BACK)
    return streaming.started([str(where(named))], errors=errors,
                             where=directory.home(agent), env=env, holding=(holding,))


def _is_a_path(named: str) -> bool:
    """Whether this provider was given as a location rather than as a name.

    The same test `core.adapters.where` makes, asked here too because `key` has to answer it before
    the program has been found — a name that will not resolve still needs a directory to have been
    named, or a turn that cannot start cannot say where it looked.
    """
    return os.sep in named or bool(os.altsep and os.altsep in named) or named.startswith("~")


def _plainly(said: str) -> str:
    """What is left of a name once anything that would not stand as a directory is taken out."""
    return "".join(one if one.isalnum() or one in "-_" else "-" for one in said).strip("-")
