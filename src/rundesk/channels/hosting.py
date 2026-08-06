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

## What crosses the seam, and which side decides it

The thread carries three things inward and this module answers two of them. A message from somebody
allowed is written down; whatever they attached is taken out of the channel's own directory and put
where the agent will read it; and the message is marked **seen**, which is the one turn state that
needs no turn — a message arriving is the whole of the event. Everything else a mark could say is
what became of a turn, and there is no provider layer here to run one.

Outward, `told` carries words already cut to size by `delivery.split` and files already vetted by
`delivery.carried`. Neither decision is made here: this is the transport, and a transport that
decided what a platform would take would be the second copy of a rule.

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
from typing import Any, Dict, List, NamedTuple, Optional, Sequence

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

#: The exit code an adapter uses for a failure that starting it again cannot fix: a token that has
#: been revoked, a close code the platform will answer with for ever. `78` is `EX_CONFIG`, which is
#: what this is, and the number is the whole of the agreement — the two sides of this seam are two
#: processes and cannot share a constant.
#:
#: **Read, and not merely written down.** Logged and then restarted on the flat ten-second hold-off,
#: a revoked Discord token is a login attempt every ten seconds — about 8,600 a day — which is
#: exactly the Cloudflare ban of this machine's own address that the adapter's close-code table was
#: written to avoid. An adapter that has said *this will not come right* is believed.
WILL_NOT_FIX = 78

#: A hold-off that does not end, which is what `WILL_NOT_FIX` earns. It is a moment far past any
#: this process will reach rather than a flag of its own, so every reader of `waiting` already
#: answers correctly and nothing had to learn a second rule.
#:
#: It lasts this gateway's lifetime and no longer, and that is the honest bound: what has to change
#: is the channel's configuration, and the credential a channel is refused for does not live in its
#: record — so there is nothing here to watch for a change. Putting it right ends with the gateway
#: being restarted, and a gateway that restarts starts this channel again.
NEVER_AGAIN = float("inf")

#: What rundesk says a turn is doing. Rundesk decides it; an adapter decides only how it looks.
#:
#: **`seen`, `working`, `done`, `stopped`, `failed` — and not `taken`, `running`, `finished`.** Two
#: vocabularies for one idea stood in this tree: the shipped adapter's marks are keyed on the first
#: and `docs/research/the-adapter-contracts.md` reproduces the previous build's second. This is the
#: one both sides of the seam already spoke, and the one whose words say what somebody actually sees
#: — a message that has been seen, an agent that is working, a turn that is done. The other set
#: describes the run's own bookkeeping, which is the half that never crosses here. Nothing consumed
#: either of them, so choosing cost nothing; leaving both standing costs a mark that never appears
#: and nobody able to say why.
#:
#: **Only `seen` has a producer, and that is not an omission.** It is the one state that does not
#: need a turn: a message arriving is the whole of the event. The other four say what became of a
#: turn, and there is no provider layer in this build to run one — so they are the adapter's to
#: render on the day something drives them.
SEEN = "seen"

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
    #: Held while one record is written to this adapter, because **two threads write to it**: the
    #: gateway's loop delivers and stops, and the thread draining its stdout marks what has just
    #: arrived. A line half written by one and finished by the other is a line the adapter cannot
    #: parse, and this seam is newline-delimited JSON — one bad line there is not one bad record.
    #: `None` on an adapter this process did not start, which is also one it never speaks to.
    saying: Optional[threading.Lock] = None


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
            _asked_to_stop(where, one)
            stuck = programs.stop(one.pid, gently_for=each * 0.6, firmly_for=each * 0.4)
            _note(where, f"channel {one.kind}: "
                         + (f"would not stop: {stuck}" if stuck else "stopped with this gateway"),
                  logs.WARNING if stuck else logs.INFO)
            _let_go(agent, where, one, watching)
    return watching


def told(agent: str, where: Path, watching: Watching, kind: str, place: str,
         pieces: List[str], sending: Sequence[naming.Sending] = ()) -> bool:
    """Send something to a place through a running adapter. `False` when there is nothing to send it.

    `False` rather than an exception: a notice that could not be delivered because the adapter is
    restarting is a fact to write down, not a reason to interrupt whatever produced it.

    `sending` is what `delivery.carried` has already approved, and it goes with the **last** piece:
    the words describing a file are what a reader wants above it, and a platform hangs an attachment
    under the message it came with. Files and no words is one record carrying no text, which the
    adapter takes; neither files nor words is nothing to send, and nothing is what is sent.
    """
    one = watching.running.get(kind)
    if one is None or one.talking is None:
        return False
    carrying = [{"name": each.name, "at": str(each.at), "bytes": each.bytes,
                 "sha256": each.sha256} for each in sending]
    saying = list(pieces) or ([""] if carrying else [])
    for nth, piece in enumerate(saying):
        record = {"do": "deliver", "id": f"{time.time():.6f}-{nth}", "place": place, "text": piece}
        if carrying and nth == len(saying) - 1:
            record["files"] = carrying
        if not _said_to(where, one, record):
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
        if held_off == NEVER_AGAIN:
            # An adapter that exited `WILL_NOT_FIX` said this cannot come right by being started
            # again. Written out rather than left to the arithmetic below, which happens to answer
            # correctly for an infinite moment: a reader has to be able to see that it is deliberate.
            continue
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
        talking = adapters.talking_to(kind, _the_environment(agent, kind, row), errors, held)
        files.write_json(record_of(agent, kind), {"kind": kind, "started_at": logs.stamp(),
                                                  "pid": talking.pid})

    # Built before the thread and handed to it, so that the one lock guarding writes to this
    # adapter is the same object on both sides of it. The stored one gains the thread afterwards;
    # the thread's own copy never reads that field.
    one = Running(kind=kind, pid=talking.pid, talking=talking, listening=None,
                  since=time.monotonic(), mine=True, saying=threading.Lock())
    listening = threading.Thread(target=_listened, name=f"channel-{kind}",
                                 args=(agent, where, one, row), daemon=True)
    listening.start()
    watching.running[kind] = one._replace(listening=listening)
    _note(where, f"channel {kind}: started as pid {talking.pid}")


def _listened(agent: str, where: Path, one: Running, row: Dict[str, Any]) -> None:
    """Read everything an adapter says, for as long as it says anything. **Never raises.**

    This is the thread the module docstring is about. It cannot fall behind the way the gateway's
    own loop would, because it does nothing but read — and it must not end the process it runs in,
    because a thread that raises takes its traceback nowhere anybody will look.
    """
    kind = one.kind
    allowed = set()
    with contextlib.suppress(Exception):
        allowed = set(kept.who_may_reach(row))
    try:
        for line in one.talking.stdout:
            if len(line) > LINE_AT_MOST:
                _note(where, f"channel {kind}: said more in one line than is read at once", logs.WARNING)
                continue
            with contextlib.suppress(Exception):
                _heard(agent, where, one, line, allowed)
    except Exception as why:                           # noqa: BLE001 — see the module docstring
        with contextlib.suppress(Exception):
            _note(where, f"channel {kind}: this gateway stopped listening to it ({why})", logs.ERROR)


def _heard(agent: str, where: Path, one: Running, line: str, allowed: set) -> None:
    """One record an adapter sent. Anything unrecognised is kept quiet rather than refused loudly."""
    kind = one.kind
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
        _arrived(agent, where, one, record, allowed)
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


def _arrived(agent: str, where: Path, one: Running, record: Dict[str, Any], allowed: set) -> None:
    """One message somebody sent. **Recorded only if they may be answered.**

    A stranger's message is never written down, and they are never told anything: replying to say
    somebody is a stranger confirms the agent is listening and spends the owner's tokens doing it.
    Nothing is recorded either, because a record of it is something an agent could later be asked
    to read.

    Then, and only for somebody who may be answered, two things go the other way: whatever they
    attached is taken in, and the message is marked as seen.
    """
    kind = one.kind
    who = str(record.get("user") or "")
    if who not in allowed:
        return
    place = str(record.get("conversation") or "")
    body = str(record.get("text") or "")
    brought = record.get("attachments")
    brought = brought if isinstance(brought, list) else []
    external = _a_text(record.get("external_id"))
    if not place:
        return
    if not body and not brought:
        return
    if brought:
        # **A message that is only a file is still a message.** Requiring text dropped it in total
        # silence — not recorded, not logged, nothing said — for somebody who was on the allow list.
        here = _taken_in(agent, where, kind, external or f"{place}-{time.time():.6f}", brought)
        if not body and not here:
            _note(where, f"channel {kind}: a message in {place} brought only files that could not "
                         f"be taken in, so there was nothing to record", logs.WARNING)
            return
        body = _also_attached(body, here)
    landed = arriving.recorded(agent, kind, place, who, body, external)
    if external:
        # **The one state a turn is not needed for.** A message arriving is the whole of the event,
        # so this is said the moment it is written down rather than when something answers it — and
        # it is said on a redelivery too, because the mark belongs to the message and an adapter
        # that has just restarted is one that no longer knows it put it up.
        _said_to(where, one, {"do": "state", "place": place, "external_id": external,
                              "state": SEEN})
    if landed.fresh:
        # There is no provider, so nothing answers this. Said plainly rather than left to look like
        # something went wrong: a release that receives and cannot reply has to say which it is.
        _note(where, f"channel {kind}: {who} said something in {place} — recorded, and nothing "
                     "answers it yet")


def _taken_in(agent: str, where: Path, kind: str, message: str,
              brought: List[Any]) -> List[Path]:
    """Take what the adapter fetched into the agent's own account of it. Hands back where each went.

    **Bounded here as well as in the adapter, and the two bounds are not one rule written twice.**
    The adapter's exists so that it does not spend a platform's bandwidth on files that will not be
    kept; this one is what actually decides, because an agent's directory is not somewhere a stranger
    gets to fill and the far side of a seam is not where that is settled.

    A file that could not be taken in is a line in the log and nothing else. It is not named in what
    the agent reads: a name in that list is a promise there is something behind it.
    """
    here: List[Path] = []
    for said in brought[:naming.PER_MESSAGE]:
        if not isinstance(said, dict):
            continue
        try:
            here.append(naming.landed(agent, kind, message, said))
        except (naming.Refused, OSError) as why:
            _note(where, f"channel {kind}: {why}", logs.WARNING)
    if len(brought) > naming.PER_MESSAGE:
        _note(where, f"channel {kind}: a message brought {len(brought)} files and only the first "
                     f"{naming.PER_MESSAGE} of them were taken in", logs.WARNING)
    return here


def _also_attached(body: str, here: List[Path]) -> str:
    """What somebody typed, and where what they attached now stands on this machine.

    The shape the previous build settled on, and the reasoning transfers whole: the brain that will
    open these runs here and holds no credential for that platform, so it is given a path and never
    a link. Said as a block after what they typed rather than folded into it, so that rundesk's own
    words and theirs stay told apart.
    """
    if not here:
        return body
    named = "\n".join(f"- {at.name}: {at}" for at in here)
    return f"{body}\n\nAttached to this message, on this machine:\n{named}".strip()


def _reaped(agent: str, where: Path, watching: Watching) -> None:
    """Take the status of any adapter that has stopped, and let go of what it held."""
    for kind, one in list(watching.running.items()):
      # One bad adapter may not stop the others being reaped. `still_running` deliberately
      # re-raises anything that is not ordinary contention, so a permissions failure on one
      # channel's lock used to end this whole loop for every channel, every beat, silently.
      # `firing._reaped` guards each item for exactly this reason and this dropped it.
      with contextlib.suppress(Exception):
        if one.mine and one.pid:
            gone = programs.collected(one.pid)
            if not gone.over:
                continue
            _note(where, f"channel {kind}: the adapter stopped"
                         + (f" with code {gone.code}" if gone.code is not None else ""),
                  logs.WARNING)
            _said_on_the_way_out(agent, where, kind)
            if gone.code == WILL_NOT_FIX:
                _let_go(agent, where, one, watching)
                _will_not_come_right(where, watching, kind)
                continue
        else:
            if still_running(agent, kind):
                continue
            _note(where, f"channel {kind}: the adapter a previous gateway started is gone",
                  logs.WARNING)
        _let_go(agent, where, one, watching)


def _asked_to_stop(where: Path, one: Running) -> None:
    """Ask an adapter to stop through the protocol before it is signalled.

    A platform is politer about a connection that says goodbye than one that vanishes, and an
    adapter that can clear a presence should be given the chance. It is asked and not waited for —
    the signal follows either way.
    """
    if one.talking is not None:
        _said_to(where, one, {"do": "stop"})


def _said_to(where: Path, one: Running, record: Dict[str, Any]) -> bool:
    """Write one record to an adapter, whole. `False` when it could not be written.

    **Under the adapter's own lock**, because the gateway's loop and the thread draining that
    adapter's stdout both write here — a delivery and the mark on a message that has just arrived —
    and this seam is newline-delimited JSON, where two half-written lines are not two damaged
    records but a stream a reader cannot find its place in again.

    A broken pipe here is ordinary: the adapter has stopped and this process has not noticed yet.
    """
    if one.talking is None:
        return False
    holding = one.saying if one.saying is not None else contextlib.nullcontext()
    try:
        with holding:
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


def _will_not_come_right(where: Path, watching: Watching, kind: str) -> None:
    """Stop starting a channel whose adapter said starting it again cannot help. **Said loudly.**

    `WILL_NOT_FIX` is `EX_CONFIG`, and an adapter answers with it for the failures where trying
    again *is* the damage: a token that has been revoked, an intent mask a platform will refuse for
    ever. Held off on the flat ten seconds instead, a revoked Discord token is around 8,600 login
    attempts a day, which earns this machine's own address a Cloudflare ban.

    Said at `ERROR` and said once, because it is the one channel failure an owner has to act on and
    nothing here will mention it again — there will be no second attempt to report.
    """
    watching.waiting[kind] = NEVER_AGAIN
    watching.complained[kind] = ""            # the next real complaint is a different sentence
    _note(where, f"channel {kind}: the adapter exited {WILL_NOT_FIX} (EX_CONFIG), which is how it "
                 f"says that starting it again cannot help — its credential or its configuration is "
                 f"what is wrong. This gateway will not start it again; put it right with `rundesk "
                 f"channels` and restart the gateway. What it said before it stopped is above.",
          logs.ERROR)


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


def _the_environment(agent: str, kind: str, row: Dict[str, Any]) -> Dict[str, str]:
    """What an adapter is started with: who it may answer, its own settings, and its credential.

    The credential is fetched by the name the channel recorded, never re-derived — agent names allow
    characters an environment variable does not, and sanitising them collides.

    **`RUNDESK_CHANNEL_HOME` is somewhere to put what it fetches**, and it is the directory this
    module already keeps that channel's lock and record in. An adapter holds the credential and so
    is the only thing that can download an attachment; it is handed somewhere to put one rather than
    left to invent a path, and what it stages there is only ever taken from inside this directory —
    see `files.landed`, which will not take a file from anywhere else.
    """
    built = {
        "RUNDESK_AGENT": agent,
        "RUNDESK_CHANNEL": str(row.get("kind") or ""),
        "RUNDESK_CHANNEL_HOME": str(at(agent, kind)),
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
