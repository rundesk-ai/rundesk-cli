"""Keeping a channel's adapter running: starting it, listening to it, and stopping it.

The same four verbs `schedules.firing` has, against the same three seams in the gateway's loop —
`settled` on the way up, `looked` every pass, `stopping` on the way out — because that shape is
already proven against a supervisor that can be killed at any moment. A sibling of it rather than a
refactor of it into something generic: two tenants is not a pattern, and the second one differs in
the part that matters.

## What differs, and it is the whole of this module

A firing is a program that answers and stops. An adapter is a program that runs for months **and is
listened to**, and a pipe nobody drains fills at 64KB — after which the adapter blocks for ever
writing into it, which looks exactly like a hang and appears only once it has said enough.

**The gateway's loop sleeps fifteen seconds at a time**, so draining on the loop *is* that bug. So:

> **A thread per adapter owns the stream. The loop owns the process.**

The thread reads lines and records them; SQLite takes its own lock, so writing from it is safe. The
loop asks only whether the child is alive, starts one that is not, and stops them all at the end.

## The claim is the check, and the child holds it

An adapter takes an exclusive `flock` on its own `lock` and **the descriptor is passed to the
child**, so the claim lives exactly as long as the child and the kernel drops it however that ends —
a clean exit, a crash, a `SIGKILL`, the machine losing power. That is what lets a gateway which came
up after the one that started an adapter know the adapter is still there, and refuse to start a
second alongside it.

## Nothing here may end a gateway

Every failure is caught and written to the agent's log. A channel that cannot start, an adapter that
crashes, a platform that is down — none is a reason to take down a gateway that is otherwise hosting
its agent, and letting one through would exit non-zero into `KeepAlive`, come straight back into the
same condition, and become the endless restart `gateways.host` is arranged to make unreachable.

Guarded with `Exception` and never `BaseException`, so that `host.Stopped` — which is deliberately
not an `Exception` — still lands.

May depend on `agents`, `core` and `utils`, and not on `gateways`: where a gateway keeps its log is
handed in, so every case here runs with no supervisor anywhere near it.
"""

import contextlib
import fcntl
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional

from rundesk.agents import directory
from rundesk.channels import adapters, arriving, kept
from rundesk.channels import files as naming
from rundesk.core import secrets
from rundesk.utils import files, locking, logs, programs

#: What one channel keeps beside itself, inside its own directory.
LOCK = "lock"
RECORD = "record.json"
ERRORS = "stderr.log"

#: When an adapter's error file is worth moving aside, and how many are kept. The same shape and the
#: same reasoning as everywhere else: a channel that reconnects noisily for a week must not be able
#: to fill a disk, and the beginning of the trouble is the part worth keeping.
ERRORS_OVER = 256 * 1024
ERRORS_KEPT = 3

#: How long after an adapter stops before another is started in its place. Long enough not to hammer
#: a platform that is refusing us, short enough that an owner does not notice. The number the build
#: this replaces settled on.
AGAIN_AFTER = 10.0

#: The least time any one adapter gets to stop, however many there are. A gateway's whole shutdown
#: is bounded by the job's `ExitTimeOut`, and channels share that budget with schedules — so the
#: share is divided rather than spent per child, and never below this.
STOPPING_LEAST = 1.0

#: How much of a line an adapter sends is read before it is refused. Not a limit on what an adapter
#: may say, only on what is held at once — a program that never writes a newline cannot grow this
#: process without bound.
LINE_AT_MOST = 1024 * 1024

#: How much of what an adapter wrote to its error stream is copied into the agent's log when it
#: stops. The whole of it stays in the file; this is what somebody reading the day's log sees.
SAID_AT_MOST = 20
SAID_LINE_AT_MOST = 500


class Running(NamedTuple):
    """One adapter this gateway is hosting.

    `mine` is the field to read first, and it means *this* process started it. An adapter adopted
    from a previous gateway is not ours to reap — a status belongs to the parent — and not ours to
    stop, because its group is not one this process may signal on the way out.
    """

    kind: str
    pid: int
    talking: Optional[programs.Talking]
    listening: Optional[threading.Thread]
    since: float
    mine: bool


class Watching(NamedTuple):
    """Every adapter this gateway knows about, and when each was last started.

    `waiting` holds the moment an adapter stopped, so the next start is held off until `AGAIN_AFTER`
    has passed. Held in memory rather than written down: it decides only whether to try again now,
    and a gateway that restarts and tries immediately has lost nothing.
    """

    running: Dict[str, Running]
    waiting: Dict[str, float]
    complained: Dict[str, str]


class Occupied(Exception):
    """Something else is already hosting this channel."""


def at(agent: str, kind: str) -> Path:
    """The directory one channel keeps everything in.

    **`naming` and not `files`.** Two modules here are called `files` — `utils.files`, which every
    other call in this module means, and `channels.files`, which owns what a name may be. Written as
    `files.plainly` this resolved to the wrong one and raised `AttributeError` inside a guard that
    correctly refuses to end a gateway, so every adapter silently never started and the reason went
    nowhere. The import is named apart so the two cannot be confused again.
    """
    return directory.channels(agent) / naming.plainly(kind)


def lock_of(agent: str, kind: str) -> Path:
    return at(agent, kind) / LOCK


def record_of(agent: str, kind: str) -> Path:
    return at(agent, kind) / RECORD


def errors_of(agent: str, kind: str) -> Path:
    return at(agent, kind) / ERRORS


def still_running(agent: str, kind: str) -> bool:
    """Whether an adapter holds this channel's claim, asked of the kernel.

    A shared probe, so two of these cannot see each other, and it **never creates the file** — a
    channel nobody has ever started must not be given a lock by the act of asking about it.
    """
    where = lock_of(agent, kind)
    if not where.is_file():
        return False
    try:
        held = os.open(str(where), os.O_RDONLY)
    except OSError:
        return False
    try:
        fcntl.flock(held, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except OSError as why:
        # **Somebody holding it and something being wrong are different answers.** `firing` already
        # asks `locking.busy` here; without it a permissions failure, `ENOLCK` or a filesystem that
        # will not lock all read as "the channel is running", which is a claim nothing has made.
        if not locking.busy(why):
            raise
        return True
    finally:
        with contextlib.suppress(OSError):
            os.close(held)
    return False


@contextlib.contextmanager
def claiming(agent: str, kind: str):
    """Hold this channel's claim for the length of the block, yielding the descriptor to pass down.

    **The lock file is never unlinked while it is held.** A `flock` lives on the inode, so removing
    the name hands it away and lets a second caller lock a fresh one — after which both believe they
    have it.
    """
    where = lock_of(agent, kind)
    where.parent.mkdir(parents=True, exist_ok=True)
    held = os.open(str(where), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as why:
            if not locking.busy(why):
                raise                       # not contention — see `still_running`
            raise Occupied(f"{agent}'s {kind} channel is already being hosted") from why
        yield held
    finally:
        os.close(held)


def settled(agent: str, where: Path) -> Watching:
    """Reckon with what a previous gateway left, before this one starts anything. **Never raises.**

    An adapter whose gateway is gone is either still running — in which case this one must not start
    a second — or over, in which case its record is stale and goes. Asked of the kernel, never of
    the record: a pid in a file is a number that is reused.
    """
    watching = Watching({}, {}, {})
    with contextlib.suppress(Exception):
        for kind in _configured(agent):
            with contextlib.suppress(Exception):
                _reckoned(agent, where, kind, watching)
    return watching


def looked(agent: str, where: Path, watching: Watching) -> Watching:
    """One pass: reap what has stopped, and start what should be running and is not.

    **Never ends the gateway.** Everything here is guarded, because a platform being down is not a
    reason to take an agent's whole gateway with it.
    """
    with contextlib.suppress(Exception):
        _reaped(agent, where, watching)
    with contextlib.suppress(Exception):
        _started_what_should_be(agent, where, watching)
    return watching


def stopping(agent: str, where: Path, watching: Watching, within: float) -> Watching:
    """Stop every adapter this gateway started, inside `within` seconds all told.

    **The budget is divided, never spent per child.** A gateway's whole shutdown has to fit inside
    the job's `ExitTimeOut`, and schedules are spending from the same window.

    Only the ones this process started. An adopted adapter is left to finish: its group is not one
    this process may signal, and a pid whose leader has been collected no longer resolves to a
    group — signalling it would reach whatever now holds that number.
    """
    mine = [one for one in watching.running.values() if one.mine and one.pid]
    if not mine:
        return watching
    each = max(STOPPING_LEAST, within / len(mine))
    for one in mine:
        with contextlib.suppress(Exception):
            _asked_to_stop(agent, where, one)
            stuck = programs.stop(one.pid, gently_for=each * 0.6, firmly_for=each * 0.4)
            _note(where, f"channel {one.kind}: "
                         + (f"would not stop: {stuck}" if stuck else "stopped with this gateway"),
                  logs.WARNING if stuck else logs.INFO)
            _let_go(agent, where, one, watching)
    return watching


def told(agent: str, where: Path, watching: Watching, kind: str, place: str,
         pieces: List[str]) -> bool:
    """Send something to a place through a running adapter. `False` when there is nothing to send it.

    `False` rather than an exception: a notice that could not be delivered because the adapter is
    restarting is a fact to write down, not a reason to interrupt whatever produced it.
    """
    one = watching.running.get(kind)
    if one is None or one.talking is None:
        return False
    for nth, piece in enumerate(pieces):
        if not _said_to(agent, where, one, {"do": "deliver", "id": f"{time.time():.6f}-{nth}",
                                            "place": place, "text": piece}):
            return False
    return True


def _said_once(where: Path, watching: Watching, kind: str, said: str) -> None:
    """Write a line down the first time, and not again until it changes.

    A channel whose adapter is not installed is a permanent condition retried on a timer, and a log
    that grows every fifteen seconds with the same sentence is the growth it was meant to report,
    arrived at from the other side. `firing._said_once` keeps the same rule for the same reason.
    """
    if watching.complained.get(kind) == said:
        return
    watching.complained[kind] = said
    _note(where, said, logs.WARNING)


def _configured(agent: str) -> List[str]:
    """Every channel this agent has, by platform. `[]` when its records cannot be read."""
    try:
        return [str(one["kind"]) for one in kept.all(agent)]
    except Exception:                                  # noqa: BLE001 — see the module docstring
        return []


def _reckoned(agent: str, where: Path, kind: str, watching: Watching) -> None:
    """Settle one channel a previous gateway may have left running."""
    if still_running(agent, kind):
        said = _read_record(agent, kind)
        watching.running[kind] = Running(
            kind=kind, pid=programs.a_pid(said.get("pid")) or 0, talking=None, listening=None,
            since=time.monotonic(), mine=False)
        _note(where, f"channel {kind}: adopted from a gateway that is gone — it is still connected, "
                     "so nothing new was started for it", logs.WARNING)
        return
    if record_of(agent, kind).is_file():
        _note(where, f"channel {kind}: the adapter a previous gateway started is gone",
              logs.WARNING)
        files.remove_one(record_of(agent, kind))


def _started_what_should_be(agent: str, where: Path, watching: Watching) -> None:
    """Start an adapter for every configured channel that has not got one."""
    now = time.monotonic()
    for kind in _configured(agent):
        if kind in watching.running:
            continue
        held_off = watching.waiting.get(kind)
        if held_off is not None and now - held_off < AGAIN_AFTER:
            continue
        try:
            _started(agent, where, kind, watching)
        except Exception as why:           # noqa: BLE001 — a channel that cannot start is one
            # channel that cannot start, never a gateway that cannot run. But it is **said and held
            # off** rather than suppressed: a bare `suppress` here sent the reason nowhere and
            # retried every fifteen seconds for ever, which is how an adapter that was never
            # installed looked exactly like one that was working.
            _said_once(where, watching, kind, f"channel {kind}: did not start — {why}")
            watching.waiting[kind] = time.monotonic()


def _started(agent: str, where: Path, kind: str, watching: Watching) -> None:
    """Start one adapter, claim its channel, and put a thread on its stream."""
    try:
        row = kept.one(agent, kind)
    except Exception as why:                           # noqa: BLE001 — a channel that cannot be
        # read is one channel that cannot start, and never a gateway that cannot run.
        _note(where, f"channel {kind}: cannot be read, so nothing was started ({why})", logs.ERROR)
        watching.waiting[kind] = time.monotonic()
        return

    with claiming(agent, kind) as held:
        errors = errors_of(agent, kind)
        errors.parent.mkdir(parents=True, exist_ok=True)
        logs.rotated(errors, ERRORS_OVER, ERRORS_KEPT)
        # Written before the spawn, carrying everything known then. A gateway killed in the window
        # before the pid lands can still *see* the adapter — the lock says so — and still refuses to
        # start a second; writing it afterwards would lose the adapter entirely.
        files.write_json(record_of(agent, kind), {"kind": kind, "started_at": logs.stamp(),
                                                  "pid": None})
        talking = adapters.talking_to(kind, _the_environment(agent, row), errors, held)
        files.write_json(record_of(agent, kind), {"kind": kind, "started_at": logs.stamp(),
                                                  "pid": talking.pid})

    listening = threading.Thread(target=_listened, name=f"channel-{kind}",
                                 args=(agent, where, kind, talking, row), daemon=True)
    listening.start()
    watching.running[kind] = Running(kind=kind, pid=talking.pid, talking=talking,
                                     listening=listening, since=time.monotonic(), mine=True)
    _note(where, f"channel {kind}: started as pid {talking.pid}")


def _listened(agent: str, where: Path, kind: str, talking: programs.Talking,
              row: Dict[str, Any]) -> None:
    """Read everything an adapter says, for as long as it says anything. **Never raises.**

    This is the thread the module docstring is about. It cannot fall behind the way the gateway's
    own loop would, because it does nothing but read — and it must not end the process it runs in,
    because a thread that raises takes its traceback nowhere anybody will look.
    """
    allowed = set()
    with contextlib.suppress(Exception):
        allowed = set(kept.who_may_reach(row))
    try:
        for line in talking.stdout:
            if len(line) > LINE_AT_MOST:
                _note(where, f"channel {kind}: said more in one line than is read at once", logs.WARNING)
                continue
            with contextlib.suppress(Exception):
                _heard(agent, where, kind, line, allowed)
    except Exception as why:                           # noqa: BLE001 — see the module docstring
        with contextlib.suppress(Exception):
            _note(where, f"channel {kind}: this gateway stopped listening to it ({why})", logs.ERROR)


def _heard(agent: str, where: Path, kind: str, line: str, allowed: set) -> None:
    """One record an adapter sent. Anything unrecognised is kept quiet rather than refused loudly."""
    said = line.strip()
    if not said:
        return
    try:
        record = json.loads(said)
    except ValueError:
        _note(where, f"channel {kind}: said something that is not a record", logs.WARNING)
        return
    if not isinstance(record, dict):
        return

    saying = record.get("say")
    if saying == "arrived":
        _arrived(agent, where, kind, record, allowed)
    elif saying == "ready":
        _note(where, f"channel {kind}: connected"
                     + (f" as {record.get('as')}" if record.get("as") else ""))
    elif saying == "gone":
        _note(where, f"channel {kind}: lost the connection ({record.get('why') or 'no reason given'})",
              logs.WARNING)
    elif saying == "note":
        _note(where, f"channel {kind}: {record.get('text')}", _how_serious(record.get("level")))
    elif saying == "failed":
        _note(where, f"channel {kind}: could not deliver — {record.get('why')}", logs.WARNING)


def _arrived(agent: str, where: Path, kind: str, record: Dict[str, Any], allowed: set) -> None:
    """One message somebody sent. **Recorded only if they may be answered.**

    A stranger's message is never written down, and they are never told anything: replying to say
    somebody is a stranger confirms the agent is listening and spends the owner's tokens doing it.
    Nothing is recorded either, because a record of it is something an agent could later be asked
    to read.
    """
    who = str(record.get("user") or "")
    if who not in allowed:
        return
    place = str(record.get("conversation") or "")
    body = str(record.get("text") or "")
    if not place or not body:
        return
    landed = arriving.recorded(agent, kind, place, who, body,
                              _a_text(record.get("external_id")))
    if landed.fresh:
        # There is no provider, so nothing answers this. Said plainly rather than left to look like
        # something went wrong: a release that receives and cannot reply has to say which it is.
        _note(where, f"channel {kind}: {who} said something in {place} — recorded, and nothing "
                     "answers it yet")


def _reaped(agent: str, where: Path, watching: Watching) -> None:
    """Take the status of any adapter that has stopped, and let go of what it held."""
    for kind, one in list(watching.running.items()):
        if one.mine and one.pid:
            gone = programs.collected(one.pid)
            if not gone.over:
                continue
            _note(where, f"channel {kind}: the adapter stopped"
                         + (f" with code {gone.code}" if gone.code is not None else ""),
                  logs.WARNING)
            _said_on_the_way_out(agent, where, kind)
        else:
            if still_running(agent, kind):
                continue
            _note(where, f"channel {kind}: the adapter a previous gateway started is gone",
                  logs.WARNING)
        _let_go(agent, where, one, watching)


def _asked_to_stop(agent: str, where: Path, one: Running) -> None:
    """Ask an adapter to stop through the protocol before it is signalled.

    A platform is politer about a connection that says goodbye than one that vanishes, and an
    adapter that can clear a presence should be given the chance. It is asked and not waited for —
    the signal follows either way.
    """
    if one.talking is not None:
        _said_to(agent, where, one, {"do": "stop"})


def _said_to(agent: str, where: Path, one: Running, record: Dict[str, Any]) -> bool:
    """Write one record to an adapter. `False` when it could not be written.

    A broken pipe here is ordinary: the adapter has stopped and this process has not noticed yet.
    """
    if one.talking is None:
        return False
    try:
        one.talking.stdin.write(json.dumps(record) + "\n")
        one.talking.stdin.flush()
        return True
    except (OSError, ValueError):
        with contextlib.suppress(Exception):
            _note(where, f"channel {one.kind}: could not be spoken to", logs.WARNING)
        return False


def _let_go(agent: str, where: Path, one: Running, watching: Watching) -> None:
    """Close what this process holds for an adapter that is over, and hold off the next start."""
    if one.talking is not None:
        for end in (one.talking.stdout, one.talking.stdin):
            with contextlib.suppress(Exception):
                end.close()
    with contextlib.suppress(OSError):
        files.remove_one(record_of(agent, one.kind))
    watching.running.pop(one.kind, None)
    watching.waiting[one.kind] = time.monotonic()


def _said_on_the_way_out(agent: str, where: Path, kind: str) -> None:
    """Copy a bounded tail of what an adapter wrote to its error stream into the agent's log.

    The whole of it stays in the file. This is the part somebody reading the day's log sees, and it
    is bounded because a program that wrote a megabyte of traceback would otherwise roll the rest of
    the day off the end of the thing they came to read.
    """
    try:
        lines = errors_of(agent, kind).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    for line in lines[-SAID_AT_MOST:]:
        if line.strip():
            _note(where, f"channel {kind}: {line.strip()[:SAID_LINE_AT_MOST]}", logs.ERROR)


def _the_environment(agent: str, row: Dict[str, Any]) -> Dict[str, str]:
    """What an adapter is started with: who it may answer, its own settings, and its credential.

    The credential is fetched by the name the channel recorded, never re-derived — agent names allow
    characters an environment variable does not, and sanitising them collides.
    """
    built = {
        "RUNDESK_AGENT": agent,
        "RUNDESK_CHANNEL": str(row.get("kind") or ""),
        "RUNDESK_SETTINGS": str(row.get("settings") or "{}"),
        "RUNDESK_ALLOW": ",".join(kept.who_may_reach(row)),
    }
    for name in _named_secrets(row):
        held = secrets.value(name)
        if held is not None:
            built[name] = held
    return built


def _named_secrets(row: Dict[str, Any]) -> List[str]:
    """The environment names this channel's credentials are kept under."""
    try:
        held = json.loads(row.get("secret_names") or "[]")
    except ValueError:
        return []
    return [str(one) for one in held] if isinstance(held, list) else []


def _read_record(agent: str, kind: str) -> Dict[str, Any]:
    """What a previous gateway wrote about an adapter, or an empty mapping."""
    how, said = files.read_json(record_of(agent, kind))
    return said if how == files.READ and isinstance(said, dict) else {}


def _a_text(said: Any) -> Optional[str]:
    """A value as text, or `None` when there was none — said-nothing is not said-empty."""
    return None if said is None else str(said)


def _how_serious(said: Any) -> str:
    """An adapter's own word for how bad something is, as one of this product's four."""
    wanted = str(said or "").strip().upper()
    return wanted if wanted in logs.LEVELS else logs.INFO


def _note(where: Path, said: str, level: str = logs.INFO) -> None:
    """Write one line into the agent's own day log, and never make the directory to do it.

    Guarded like `firing._note` and for the same reason: `logs.note` creates the directory it writes
    into, so a gateway whose agent has been taken away would put it back in the act of complaining
    that it is gone.
    """
    with contextlib.suppress(Exception):
        if where.parent.is_dir():
            logs.note(where, said, level)
