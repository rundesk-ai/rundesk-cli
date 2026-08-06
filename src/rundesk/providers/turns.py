"""One turn: what it resolved, what it ran, and the account it left behind.

The only module here that knows the others exist. `protocol` is the vocabulary, `adapters` is the
program, `environment` is what it is told, `instructions` is what it reads, `streaming` is how it is
read, and `kept` is where it is written down — each of those is about one thing and none of them
knows about the rest, which is what lets every one be proved on its own. This is where they meet:

    claim -> resolve -> write down what was resolved -> compose -> run -> write down what it said
          -> keep where the conversation got to -> settle

## One turn at a time in one conversation, and the kernel is what says so

A turn takes an exclusive `flock` on the conversation's own lock and **hands the descriptor to the
adapter**. A `flock` belongs to the open file description, so it lives exactly as long as the adapter
and everything it started, and the kernel drops it however they end — a clean exit, a crash, a
`SIGKILL`, the machine losing power. Nothing has to be tidied up for the answer to become correct.

Three things fall out of that, and each is a defect in the build this replaces:

**A second turn cannot begin in a conversation that is busy**, across processes. `rundesk ask` typed
at a terminal and a gateway answering a channel compete for the same lock, correctly, with no
coordination between them — where the old build funnelled inside the gateway and a terminal knew
nothing about it.

**A turn is never shown as running when it is not.** The question is put to the kernel, never to
something a process wrote down: a pid in a file is a number that is reused, and a gateway killed
outright leaves that number pointing at a stranger's program.

**A gateway that came up after the one that started a turn still knows work is going on.** It cannot
reap it — a status belongs to the parent — so what it can honestly say is `stopped`, and that is what
it says.

## What is written down, and when

**The turn row is written before the adapter starts**, because a turn that died on its way to the
brain still has to show what somebody asked for. **Nothing reaches a brain that the account does not
show**: the instructions are fingerprinted onto the turn before anything is started, and every word
said into a running turn is written down before it is sent.

**A turn that was begun is settled, whatever happens next.** That is a context manager entered
outside everything else, because the path it exists for cannot be caught by the body it wraps — a
gateway standing down takes this process with it, and a turn left `working` in an owner's records for
ever is one that `rundesk turns` goes on showing as in flight with nothing doing it.

## What a caller gets while it runs

`watching` is handed every record as it arrives, so a surface can show a turn as it happens. The
account is written whether or not anybody is watching, and a watcher that raises is the watcher's
own problem and never the turn's.
"""

import contextlib
import fcntl
import json
import os
import threading
import time
from typing import Any, Callable, Dict, Iterable, Iterator, List, NamedTuple, Optional, Tuple

from rundesk.agents import directory, records
from rundesk.channels import arriving
from rundesk.providers import adapters, environment, instructions, kept, protocol, streaming
from rundesk.skills import grants
from rundesk.utils import lines, locking, logs

#: The one way finding a provider fails, named here so a caller has one thing to be ready for.
NotRunnable = adapters.NotRunnable

#: What rundesk itself writes into a turn's own account, beside what the brain reported. Each is
#: lifecycle bookkeeping about an execution rather than a new shape of owner data.
SENT = "sent"
INSTRUCTIONS = "instructions"
LOST = "lost"
UNKNOWN = "unknown"

#: What a turn that produced nothing is recorded as having gone wrong. Prose rather than one of the
#: closed words, because **no brain classified this** — rundesk noticed it, and a word from that set
#: would claim an adapter reported something it did not.
NOTHING_SAID = "the turn ended without an answer"

#: How much of one record's own words is kept. A tool result can hold a whole file, a credential or a
#: private path; the contract already asks an adapter to summarise, and this is the backstop against
#: one that does not.
AN_EVENT_AT_MOST = 4000

#: How long a turn waits for the conversation's claim before giving up. **Zero**: a lock this cannot
#: have is not a busy moment to sit out, it is the answer — something else is already answering in
#: this conversation, and a second turn must not begin.
NEVER_WAITS = 0.0


class Busy(Exception):
    """Something is already answering in this conversation.

    Named rather than answered as a boolean, because the two callers do different things with it: a
    gateway writes a line and carries on, and a person who typed `rundesk ask` is told to their face.
    """


class Request(NamedTuple):
    """Everything a turn is admitted with.

    A value object rather than fourteen arguments: the build this replaces took thirty, and a caller
    that got two of them the wrong way round would hand a brain another agent's home with nothing
    going wrong until much later.
    """

    agent: str
    prompt: str
    conversation: int
    trigger: str = instructions.A_PERSON_ASKED
    access_mode: str = protocol.ACCESS_WORK
    model_name: Optional[str] = None
    schedule_id: Optional[int] = None
    #: Start a new conversation on the brain even if this one has a handle.
    fresh: bool = False
    #: Where the answer is written back, for a conversation that has a place of its own.
    source: str = arriving.FROM_SCHEDULE
    place: str = ""
    #: Instruction layers this caller wants added, as `(name, text)`.
    additions: Tuple[Tuple[str, str], ...] = ()


class Outcome(NamedTuple):
    """What became of one turn, once it is over."""

    turn: int
    turn_status: str
    reply: str = ""
    last_thought: str = ""
    failure_code: Optional[str] = None
    failure_message: Optional[str] = None
    usage: protocol.Usage = protocol.Usage()
    files: Tuple[Dict[str, Any], ...] = ()
    #: Which brain answered. Named on the outcome as well as in the record, because a surface
    #: showing what a turn cost has to say which brain it cost it on — read off the turn's own
    #: resolution rather than asked again, so a surface and the ledger cannot name two.
    provider_name: str = ""
    #: How long the turn took, from admission to settled, on a **monotonic** clock. Never a
    #: difference of wall-clock stamps: those move when the machine's time is corrected, and a turn
    #: that ran for two minutes across one of those reported a negative duration.
    elapsed_seconds: Optional[float] = None

    @property
    def worked(self) -> bool:
        """Whether this is a turn anybody got an answer out of."""
        return self.turn_status == kept.DONE


@contextlib.contextmanager
def claiming(agent: str, conversation: int) -> Iterator[int]:
    """Take this conversation's claim for the length of the block. `Busy` when somebody has it.

    **The claim is the check.** Anything that asked whether a turn was running and then started one
    would have two decisions with a gap between them, and a second turn can arrive inside it.

    Yields the descriptor, because the caller is about to hand it to the adapter. On the way out this
    process's own copy is closed, which is what lets go of the claim *here* — the adapter's copy keeps
    it for as long as the adapter lives.

    **The file itself is left alone.** A lock lives on the inode, so unlinking it hands the name away
    and lets the next claim lock a fresh inode while this one is still held.
    """
    at = adapters.lock_of(agent, conversation)
    at.parent.mkdir(parents=True, exist_ok=True)
    held = os.open(at, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as why:
            if not locking.busy(why):
                raise
            raise Busy(f"something is already answering in conversation {conversation}") from why
        yield held
    finally:
        os.close(held)


def busy(agent: str, conversation: int) -> bool:
    """Whether a turn is running in this conversation now. Asked of the kernel.

    **Probed with a shared lock**, because an exclusive probe conflicts with another *probe* — two
    people asking at the same moment would each read the other as a running turn.

    **Never creates the file.** A lock that is not there means this conversation has never had a
    turn, and a question that writes is a question that fails on a read-only disk.
    """
    try:
        asked = os.open(adapters.lock_of(agent, conversation), os.O_RDONLY)
    except OSError:
        return False
    try:
        fcntl.flock(asked, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except OSError as why:
        return locking.busy(why)
    finally:
        os.close(asked)
    return False


class Words:
    """Words for a turn that is already running, and whether it will still take one.

    **A caller with something to say cannot hold the conversation's claim** — the turn running in it
    does — so it needs somewhere to put a word that the turn will read. This is that place, and it
    is the whole of what one turn publishes about itself while it runs.

    `open` is the part that matters, and it is not a formality. A turn settles while somebody is
    still typing at it, and the moment it does, a word handed here would be read by nobody. So this
    says **no** the instant the turn stops taking words, and whoever was speaking finds out in time
    to do something about it rather than being told it was delivered.
    """

    def __init__(self) -> None:
        self.watching = threading.Condition()
        self.words: List[str] = []
        self.open = True

    def say(self, word: str) -> bool:
        """Put one word in. **False when the turn will not read it** — and the caller must act."""
        with self.watching:
            if not self.open:
                return False
            self.words.append(word)
            self.watching.notify_all()
            return True

    def close(self) -> None:
        """No more words will be read. Said once the turn is over, and never taken back."""
        with self.watching:
            self.open = False
            self.watching.notify_all()

    def each(self):
        """Every word, as it arrives, until the turn stops taking them."""
        at = 0
        while True:
            with self.watching:
                self.watching.wait_for(
                    lambda so_far=at: so_far < len(self.words) or not self.open)
                if at >= len(self.words):
                    return
                word, at = self.words[at], at + 1
            yield word


#: The turns running right now that will still take a word, by the conversation each is running in.
#: **Only the ones that can be steered are here** — a turn whose brain reads nothing after its
#: prompt has nothing to publish, and offering one would let a caller believe a word landed.
#:
#: In memory and deliberately: this answers *is there a turn in this process to speak to*, and a
#: turn in another process is not one, however it was written down. What crosses processes is the
#: lock, which is the kernel's and is what `busy` asks.
_speaking_to: Dict[tuple, Words] = {}
_speaking_to_lock = threading.Lock()


def also_say(agent: str, conversation: int, word: str) -> bool:
    """Put a word into the turn already running in this conversation. **False if none took it.**

    False has three causes and one meaning. There may be no turn running here; there may be one
    whose brain cannot be steered; or there may have been one a moment ago that has since settled.
    All three mean the same thing to whoever is holding the word — **nobody is going to read it, so
    it is still yours** — and a caller that treated any of them as delivery would drop a message
    somebody sent.
    """
    with _speaking_to_lock:
        speaking = _speaking_to.get((agent, conversation))
    return bool(speaking and speaking.say(word))


@contextlib.contextmanager
def _reachable(agent: str, conversation: int, words: Optional[Words]):
    """Publish this turn as one that will take a word, for exactly as long as that is true.

    Closed *before* it is taken out of the registry, and both in a `finally`: a turn that vanished
    from the registry while still open would leave whoever is mid-`say` believing a word landed,
    and the ordering is the only thing that makes `also_say`'s answer honest.
    """
    if words is None:
        yield
        return
    with _speaking_to_lock:
        _speaking_to[(agent, conversation)] = words
    try:
        yield
    finally:
        words.close()
        with _speaking_to_lock:
            if _speaking_to.get((agent, conversation)) is words:
                del _speaking_to[(agent, conversation)]


def run(request: Request, watching: Optional[Callable[[Dict[str, Any]], None]] = None,
        saying: Optional[Iterable[str]] = None) -> Outcome:
    """Run one turn and write down everything about it. **The claim is taken here.**

    `watching` is handed every record the brain reported, as it arrives. `saying` is words to put
    into a turn already running, and reaches a brain only if that brain said it can be steered.

    A caller that passes no `saying` still gets a steerable turn published to `also_say`, so a
    message arriving on a channel mid-turn reaches the brain that is working on it. A caller that
    passes its own — the terminal, which has somebody typing — keeps it and is not published.
    """
    with claiming(request.agent, request.conversation) as held:
        return _held(request, held, watching, saying)


def _held(request: Request, held: int, watching, saying) -> Outcome:
    """One turn, with the conversation already claimed."""
    agent = request.agent
    # **Resolved before anything is written down.** A provider nothing stands behind is a turn that
    # cannot start, and a row saying one was admitted would be a record of something that never was.
    settled = records.read(directory.records(agent))
    provider_name = str(settled.get("provider_name") or "")
    adapters.where(provider_name)
    settings = _as_settings(settled.get("agent_settings"))
    can = protocol.parse_capabilities(adapters.capabilities(provider_name, settings))
    resume = None if request.fresh else kept.get_session(agent, request.conversation, provider_name)

    prompt = instructions.build(trigger=request.trigger, variables=_about(request, provider_name),
                                additions=request.additions)
    # **From admitted to settled** (R-DIS-24) — what somebody waiting actually experienced, which
    # starts here and not when the brain was reached: resolving a provider and building the prompt
    # are part of the wait. Monotonic, so a clock correction mid-turn cannot make it negative.
    began = time.monotonic()
    turn = kept.add_turn(agent, {
        "conversation_id": request.conversation,
        "schedule_id": request.schedule_id,
        # **Written beside the id, because the id does not survive the schedule.** The foreign key
        # is `ON DELETE SET NULL`, so a schedule taken away detaches every turn it ever ran and the
        # ledger forgets who spent the cost. The name is derived here already for the layers.
        "schedule_name": _schedule_name(request) or None,
        "provider_name": provider_name,
        "model_name": request.model_name,
        "access_mode": request.access_mode,
        "provider_capabilities": json.dumps(can, sort_keys=True),
        "session_resumed": 1 if resume else 0,
        "instructions_sha256": prompt.sha256,
        "instructions_bytes": prompt.total_bytes,
    })

    with _settled_whatever_happens(agent, turn) as settling:
        kept.add_turn_record(agent, turn, INSTRUCTIONS, {
            "sha256": prompt.sha256,
            "layers": [{"name": one.name, "bytes": one.bytes_used} for one in prompt.layers],
        })
        raw = adapters.raw_of(agent, request.conversation)
        began_at = _how_big(raw)
        told = environment.for_turn(
            agent=agent, home=directory.home(agent),
            provider_home=adapters.home(agent, provider_name),
            skills=grants.where(agent), turn=turn, access_mode=request.access_mode,
            raw=raw, model=request.model_name or settled.get("model_name"), resume=resume,
            settings=settings,
            preface=prompt.text, owners=environment.owners_own())
        # **A turn nobody passed words to is still one a channel can speak into.** The words go
        # somewhere `also_say` can reach for exactly as long as this turn will read them.
        reachable = Words() if can["steer"] and saying is None else None
        with _reachable(agent, request.conversation, reachable):
            said, stream = _the_brain(request, provider_name, told, turn, held, can, watching,
                                      saying if saying is not None else
                                      (reachable.each() if reachable else None), reachable)
        settling.update(_became(request, turn, said, stream, can, provider_name,
                                began_at, _how_big(raw), time.monotonic() - began))
    return settling.outcome


def _the_brain(request: Request, provider_name: str, told: Dict[str, str], turn: int, held: int,
               can: Dict[str, bool], watching, saying,
               reachable: Optional[Words] = None) -> Tuple[List[Dict[str, Any]], Any]:
    """Start the adapter, feed it the turn, and write down every record it answers with.

    **What is sent is written before it is sent.** A word put into a turn that the account does not
    show makes the account a lie, and it is invisible precisely because it *is* the account.
    """
    agent = request.agent
    stream = adapters.talking_to(provider_name, told, agent, request.conversation, held)
    said: List[Dict[str, Any]] = []
    speaking = None
    try:
        # **Bounded like every record read off the brain.** A prompt is not smaller for
        # being rundesk's own, and a schedule with a long one writes this row every time
        # the clock reaches it.
        kept.add_turn_record(agent, turn, SENT, _bounded({"text": request.prompt}))
        if can["steer"]:
            # Held open for as long as the turn lasts, so nothing can mean "the prompt ended" any
            # more — and records rather than plain text, because a brain that reads to the end of its
            # input would wait for an end that is not coming.
            stream.say(protocol.build_say_line(request.prompt))
            speaking = _speaking(agent, turn, stream, saying)
        else:
            # Told there is no more coming, so a brain that reads its input to the end can answer.
            stream.say(request.prompt)
            stream.no_more()
        for one in stream.records():
            _heard(agent, turn, one, said, watching)
    finally:
        # **Nothing may be taken from here on, and this is the first thing teardown does.**
        # `stream.stop()` below stops accepting writes as its own first act and can then spend
        # several seconds ending a brain that has gone quiet. Left open across that, this turn is
        # still published as one that will take a word — so a message arriving on a channel is
        # accepted, reported to the person as said into the running turn, and then refused by the
        # stream and written down as lost. The person is never told, and nothing asks again.
        #
        # Closing here also ends `each()`, which is what lets the join below actually finish rather
        # than time out against a feeder still waiting for a word that is never coming.
        if reachable is not None:
            reachable.close()
        if speaking is not None:
            speaking.join(timeout=1.0)
        stream.stop()
    return said, stream


def _speaking(agent: str, turn: int, stream, saying) -> Optional[threading.Thread]:
    """Put words into a turn that is already running, from a thread of its own.

    On its own thread because the caller's is draining records: a person typing and a brain talking
    happen at the same time, and a turn that could only do one of them at once would deadlock the
    first time somebody interrupted it.

    **Nothing that goes wrong in here is allowed to be silent.** A thread whose exception nobody
    retrieves failed invisibly, so a word that could not be said is written into the account as a
    loss rather than leaving the turn reporting that it was fine.
    """
    if saying is None:
        return None

    def speak() -> None:
        try:
            for word in saying:
                kept.add_turn_record(agent, turn, SENT,
                                     _bounded({"text": word, "mid_turn": True}))
                if not stream.say(protocol.build_say_line(word, protocol.STEERING_CONTEXT)):
                    kept.add_turn_record(agent, turn, LOST, {"lost_count": 1,
                                                             "reason": "it had already finished"})
                    return
        except Exception as why:                       # noqa: BLE001 — see the docstring
            with contextlib.suppress(Exception):
                kept.add_turn_record(agent, turn, LOST,
                                     {"lost_count": 1, "reason": f"not said: {why}"})
        finally:
            # **Whatever happened, the brain is told there is no more coming.** A steerable brain
            # reads until its input closes; leaving it open because *we* went wrong is a turn that
            # never ends, waiting on somebody who has already stopped speaking.
            with contextlib.suppress(Exception):
                stream.no_more()

    speaking = threading.Thread(target=speak, name=f"turn-{turn}-saying", daemon=True)
    speaking.start()
    return speaking


def _heard(agent: str, turn: int, one, said: List[Dict[str, Any]], watching) -> None:
    """One thing off the stream, written down and handed on. **Never raises.**

    A record of a kind this release does not know keeps its place in the order and its own words, so
    an adapter can be ahead of rundesk and a vendor's change shows up as visible drift.
    """
    if isinstance(one, lines.Gap):
        kept.add_turn_record(agent, turn, LOST,
                             {"lost_count": one.lost_count, "reason": one.reason})
        return
    record = protocol.parse_record(one)
    if record is None:
        kept.add_turn_record(agent, turn, UNKNOWN, {}, raw_line=str(one)[:AN_EVENT_AT_MOST])
        return
    said.append(record)
    if record["type"] not in ("text",):
        # `text` is gathered and written as one message at the end: a row per fragment is a history
        # nobody can read back and a search that matches half a sentence.
        kept.add_turn_record(agent, turn, record["type"], _bounded(record))
    if watching is not None:
        with contextlib.suppress(Exception):
            watching(record)


def _became(request: Request, turn: int, said: List[Dict[str, Any]], stream,
            can: Dict[str, bool], provider_name: str, began_at: int, ended_at: int,
            elapsed: Optional[float] = None) -> Dict[str, Any]:
    """What this turn came to, and everything the records keep about it."""
    agent = request.agent
    reply = protocol.reply(said)
    answered = protocol.has_answer(said)
    brain_said = protocol.brain_said_ok(said)
    gone = stream.outcome()
    used = protocol.usage_of(said)

    if reply.strip():
        arriving.said_by_agent(agent, request.source, request.place or agent, reply, turn=turn)
    handle = protocol.resume_handle(said)
    if handle and can["resume"]:
        kept.save_session(agent, request.conversation, provider_name, handle)

    status = kept.DONE
    code = protocol.failure_code(said)
    message = protocol.failure_message(said)
    if stream.stop_reason:
        # **Which of the two it was, asked of the stream rather than guessed from its prose.** A
        # turn rundesk gave up waiting on is a timeout and needs a person; one whose pipe could not
        # be read is a fault in this process, which is closer to a crash and worth another attempt.
        # Reported alike, an I/O failure reached an owner as "this timed out" and as a word that
        # says trying again will not help.
        status = kept.FAILED
        code = (protocol.CRASHED if stream.stop_code == streaming.COULD_NOT_BE_READ
                else protocol.TIMED_OUT)
        message = message or stream.stop_reason
    elif brain_said is False or code is not None:
        status = kept.FAILED
    elif brain_said is None:
        # No `done` at all is the shape a killed adapter leaves, and nothing here may declare such a
        # turn over on the brain's behalf.
        status, code = kept.STOPPED, protocol.CRASHED
        message = message or _trouble(stream)
    elif not answered:
        # **A program exiting well is not an answer.** Measured on a live gateway: `done ok:true`,
        # four zero counters, fourteen milliseconds, and nothing said — recorded as finished, and the
        # question that caused it consumed.
        status, message = kept.FAILED, NOTHING_SAID

    return {
        "outcome": Outcome(turn=turn, turn_status=status, reply=reply,
                           last_thought=protocol.last_thought(said), failure_code=code,
                           failure_message=message, usage=used,
                           files=tuple(protocol.file_records(said)),
                           provider_name=provider_name, elapsed_seconds=elapsed),
        "values": {
            "exit_code": gone.code,
            "failure_code": code,
            "failure_message": (message or "")[:AN_EVENT_AT_MOST] or None,
            # **The model that answered, not the one asked for.** Written at settlement rather
            # than at admission because only the brain knows which one really ran, and left alone
            # when it named none so a requested model is not erased by a brain that stayed quiet.
            **({"model_name": used.model_name} if used.model_name else {}),
            "usage_reported": 1 if used.usage_reported else 0,
            "input_tokens": used.input_tokens, "output_tokens": used.output_tokens,
            "cache_read_tokens": used.cache_read_tokens,
            "cache_write_tokens": used.cache_write_tokens,
            "context_tokens": used.context_tokens,
            "unknown_records": _counted(agent, turn, UNKNOWN),
            "lost_records": _counted(agent, turn, LOST),
            "raw_offset_start": began_at, "raw_offset_end": ended_at,
        },
    }


class _Settling:
    """What a turn came to, and whether anything has said so yet."""

    def __init__(self):
        self.outcome = None
        self.values: Dict[str, Any] = {}

    def update(self, became: Dict[str, Any]) -> None:
        self.outcome = became["outcome"]
        self.values = became["values"]


@contextlib.contextmanager
def _settled_whatever_happens(agent: str, turn: int) -> Iterator[_Settling]:
    """Leave no turn recorded as still working once nothing is doing it.

    **The path this exists for cannot be caught by the body it wraps.** A gateway standing down takes
    this process with it, and a turn that had been admitted would stay `working` in an owner's own
    records for ever — `rundesk turns` going on showing a turn in flight that nothing is doing, with
    no restart clearing it because nothing afterwards knows it was ever begun.

    Written even while the process is being taken down, so it is kept as narrow as it can be: one
    row, no reading, and anything that goes wrong swallowed. A settlement that raised on the way out
    of a cancelled turn would replace one bad record with a worse traceback.
    """
    settling = _Settling()
    try:
        yield settling
    finally:
        with contextlib.suppress(Exception):
            if settling.outcome is None:
                kept.finish_turn(agent, turn, kept.STOPPED,
                                 {"failure_code": protocol.CANCELLED,
                                  "failure_message": "this turn was stopped before it settled"})
            else:
                kept.finish_turn(agent, turn, settling.outcome.turn_status, settling.values)


def _about(request: Request, provider_name: str) -> Dict[str, object]:
    """The variables a layer may read, for this turn."""
    return {
        "agent_name": request.agent,
        "agent_home": str(directory.home(request.agent)),
        "provider_name": provider_name,
        "access_mode": request.access_mode,
        "schedule_name": _schedule_name(request),
        "conversation_id": request.conversation,
    }


def _schedule_name(request: Request) -> str:
    """What the schedule that caused this turn is called, and nothing when no schedule did.

    **The schedule's name, and nothing else's.** `place` is a Discord room on a channel turn and the
    agent's own name at a terminal, so putting either behind a name like this is a value that is
    wrong the day a layer starts reading it.

    Derived in one place because it is now read twice: the layers are handed it for this turn, and
    the turn's own row keeps it so the ledger still says which schedule ran once that schedule has
    been taken away. Two derivations of one fact are two things that can come to disagree.
    """
    return request.place if request.schedule_id else ""


def _as_settings(said: Any) -> Optional[str]:
    """Whatever the owner set for this agent, as the one object an adapter is handed.

    **Not read on the way past.** rundesk defines no key in it: what an owner set is between them and
    their brain, and a rundesk that understood one of these would be a rundesk with a vendor in it.
    Written back out sorted so the same settings are the same bytes every turn, which is what lets
    one turn be compared with another.

    Anything that is not an object is left out rather than passed on — an adapter told its settings
    are the number seven would do something odd with that, and nothing did.
    """
    if not said:
        return None
    try:
        got = json.loads(said)
    except (TypeError, ValueError):
        return None
    return json.dumps(got, sort_keys=True) if isinstance(got, dict) and got else None


def _bounded(record: Dict[str, Any]) -> Dict[str, Any]:
    """One record, small enough to keep. Marked when it was cut, so nothing reads as whole."""
    said = json.dumps(record, sort_keys=True)
    if len(said) <= AN_EVENT_AT_MOST:
        return record
    kept_of_it = dict(record)
    for name in sorted(kept_of_it):
        if isinstance(kept_of_it[name], str) and len(kept_of_it[name]) > 200:
            kept_of_it[name] = kept_of_it[name][:200]
    kept_of_it["truncated"] = True
    return kept_of_it


def _counted(agent: str, turn: int, of_a_kind: str) -> int:
    """How many records of one kind this turn left, asked of the records rather than remembered.

    Counting what was written beats counting as it goes: a record the account did not accept is not
    one this number may claim, and the two would drift the first time a write was refused.
    """
    try:
        return sum(1 for one in kept.list_turn_records(agent, turn)
                   if one["record_type"] == of_a_kind)
    except Exception:                                  # noqa: BLE001 — a count that cannot be taken
        # must not be the reason a turn fails to settle; nothing downstream branches on it.
        return 0


def _trouble(stream) -> str:
    """The last few things the adapter said went wrong, for a turn that has to explain itself."""
    tail = stream.errors_tail()
    return " / ".join(tail[-3:]) if tail else "the brain stopped without saying it had finished"


def _how_big(one) -> int:
    """How much has been written to a file so far. `0` when there is nothing there yet."""
    try:
        return one.stat().st_size
    except OSError:
        return 0


def note(agent: str, said: str, level: str = logs.INFO) -> None:
    """One line in the agent's own log, for whoever started this turn.

    Here rather than at each call site so that a turn started by a gateway, by a schedule and by a
    person all land in the same day file, in the same words.
    """
    with contextlib.suppress(Exception):
        logs.note(directory.logs(agent), said, level)

