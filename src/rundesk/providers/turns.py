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
import sqlite3
import threading
import time
from typing import Any, Callable, Dict, Iterable, Iterator, List, NamedTuple, Optional, Tuple

from rundesk.agents import directory, records
from rundesk.channels import arriving
from rundesk.core import paths
from rundesk.providers import (
    accounts,
    adapters,
    environment,
    instructions,
    kept,
    protocol,
    streaming,
    team,
)
from rundesk.skills import grants
from rundesk.utils import lines, locking, logs

#: The one way finding a provider fails, named here so a caller has one thing to be ready for.
NotRunnable = adapters.NotRunnable

#: What rundesk itself writes into a turn's own account, beside what the brain reported. Each is
#: lifecycle bookkeeping about an execution rather than a new shape of owner data.
SENT = "sent"
INSTRUCTIONS = "instructions"
ADMITTED = "admitted"

#: The three kinds a turn counts for ever, taken from `kept` because the columns they move are its
#: and a word spelled twice is two words that come to disagree.
#:
#: **`LOST` and `UNSENT` are opposite directions and never one number.** `LOST` is a record the brain
#: sent that never arrived — half of how a vendor moving underneath rundesk becomes visible — and
#: `UNSENT` is a word rundesk could not put into the turn, which is an ordinary end-of-turn race and
#: says nothing about the adapter at all. They shared a word and a column, so a person steering a
#: turn that had just finished was told their adapter had drifted.
LOST = kept.LOST
UNKNOWN = kept.UNKNOWN
UNSENT = kept.UNSENT

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

#: How often an active delegated turn looks for durable guidance written by another process. Short
#: enough to steer the work in progress, but not a busy loop against the agent's SQLite account.
GUIDANCE_EVERY = 0.2

#: Pending delegation words placed into one provider turn. At least the oldest whole message is
#: always kept, even when that message exceeds this soft aggregate bound.
DELEGATED_PROMPT_AT_MOST = 128 * 1024

#: Pending messages one delegated pickup may claim. Kept far below every supported SQLite variable
#: ceiling because the exact ids become one atomic `UPDATE`.
DELEGATED_MESSAGES_AT_MOST = 200


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
    #: Which of `instructions`' situation blocks this turn reads — the block itself, not a name
    #: for one. There is no table turning a name back into a block, because there was nothing else
    #: a name was ever used for.
    situation: str = instructions.USER_TO_AGENT
    access_mode: str = protocol.ACCESS_WORK
    model_name: Optional[str] = None
    schedule_id: Optional[int] = None
    #: Stable schedule identity when `place` is an invocation-specific source id.
    schedule_name: str = ""
    #: Start a new conversation on the brain even if this one has a handle.
    fresh: bool = False
    #: Where the answer is written back, for a conversation that has a place of its own.
    source: str = arriving.FROM_SCHEDULE
    place: str = ""
    #: Instruction layers this caller wants added, as `(name, text)`.
    additions: Tuple[Tuple[str, str], ...] = ()
    #: Which delegation this turn is answering, or `None` when it is answering nobody. Reaches the
    #: brain's environment, where a `rundesk ask` run from inside the turn reads it and refuses —
    #: which is what makes depth one enforceable rather than merely asked for.
    answering: Optional[str] = None
    #: Which agent handed this turn its task, for the layer that names them. **Required whenever
    #: `situation` is `AGENT_TO_AGENT`**: that block is four sentences about who asked and where
    #: the answer goes, and without this every one of them reaches the brain saying `{caller_agent}`.
    caller_agent: Optional[str] = None
    #: Inbound messages this turn is answering. Delegated guidance uses this durable boundary so a
    #: reply cannot accidentally consume guidance that arrived after the turn began.
    inbound_messages: Tuple[int, ...] = ()
    #: Lifecycle recovery resumes the exact prior session only while its provider and instructions
    #: remain safe; otherwise it must still wake this conversation in a fresh provider session.
    lifecycle_continuation: bool = False
    #: The brain the originating turn used. A configured-provider change requires a fresh wake.
    expected_provider: Optional[str] = None
    #: The original preface fingerprint. A mismatch requires a fresh wake under current rules.
    expected_instructions: Optional[str] = None
    #: A provider resolved before this turn claims its conversation. Appended to preserve the
    #: positional shape older callers may use; ``None`` keeps ordinary late binding to the agent's
    #: durable configuration.
    provider_name: Optional[str] = None
    #: The originating additional account. A mismatch is as unsafe as a provider mismatch.
    expected_provider_alias: Optional[str] = None
    #: The alias admitted with an explicit provider, or ``None`` for its implicit default.
    provider_alias: Optional[str] = None


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
    provider_alias: Optional[str] = None
    #: How long the turn took, from admission to settled, on a **monotonic** clock. Never a
    #: difference of wall-clock stamps: those move when the machine's time is corrected, and a turn
    #: that ran for two minutes across one of those reported a negative duration.
    elapsed_seconds: Optional[float] = None

    @property
    def worked(self) -> bool:
        """Whether this is a turn anybody got an answer out of."""
        return self.turn_status == kept.DONE


class _TurnAdmission(NamedTuple):
    """Resolved turn state whose account reference and row were decided under one install lock."""

    settled: Dict[str, Any]
    provider_name: str
    provider_alias: Optional[str]
    account_home: Any
    settings: Optional[str]
    effective_model: Optional[str]
    can: Dict[str, Any]
    teammates: str
    skill_names: str
    prompt: instructions.Prompt
    resume: Optional[str]
    began: float
    turn: int


@contextlib.contextmanager
def claiming(agent: str, conversation: int, waiting: bool = False) -> Iterator[int]:
    """Take this conversation's claim for the length of the block. `Busy` when somebody has it.

    **The claim is the check.** Anything that asked whether a turn was running and then started one
    would have two decisions with a gap between them, and a second turn can arrive inside it.

    Yields the descriptor, because the caller is about to hand it to the adapter. On the way out this
    process's own copy is closed, which is what lets go of the claim *here* — the adapter's copy keeps
    it for as long as the adapter lives.

    **The file itself is left alone.** A lock lives on the inode, so unlinking it hands the name away
    and lets the next claim lock a fresh inode while this one is still held.
    """
    with locking.only_one(paths.work_admission_lock(), guarding="admitting provider work"):
        at = adapters.lock_of(agent, conversation)
        at.parent.mkdir(parents=True, exist_ok=True)
        held = os.open(at, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            try:
                fcntl.flock(held, fcntl.LOCK_EX | (0 if waiting else fcntl.LOCK_NB))
            except OSError as why:
                if not locking.busy(why):
                    raise
                raise Busy(f"something is already answering in conversation {conversation}") from why
        except BaseException:
            os.close(held)
            raise
    try:
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
    return standing(agent, conversation) is True


def standing(agent: str, conversation: int) -> Optional[bool]:
    """Whether this conversation is active; ``None`` when the kernel cannot be asked.

    The shared status probe takes the same brief admission boundary as an exclusive claim. Without
    it, a turn arriving during the probe can read that probe as another turn and be refused as busy.
    """
    with locking.only_one(paths.work_admission_lock(), guarding="probing provider work"):
        return locking.is_held(adapters.lock_of(agent, conversation))


def activity(agent: str) -> Optional[List[str]]:
    """Every held conversation claim, or ``None`` when all claims cannot be inspected.

    Enumerates lock files rather than unfinished database rows. The kernel claim is taken before
    the row is written, deliberately, and an updater observing that admission window must still see
    the turn that already owns its conversation.
    """
    with locking.only_one(paths.work_admission_lock(), guarding="probing provider work"):
        try:
            conversations = list(directory.conversations(agent).iterdir())
        except FileNotFoundError:
            return []
        except OSError:
            return None
        active = []
        for conversation in conversations:
            held = locking.is_held(conversation / adapters.LOCK)
            if held is None:
                return None
            if held:
                active.append(conversation.name)
        return sorted(active)


class Admission:
    """Whether a word queued for a live turn actually crossed the provider boundary."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._settled = threading.Event()
        self._accepted: Optional[bool] = None

    def accepted(self) -> None:
        """The provider accepted the word. Safe when two teardown paths arrive together."""
        with self._lock:
            if self._settled.is_set():
                return
            self._accepted = True
            self._settled.set()

    def refused(self) -> None:
        """The provider did not accept the word, so its durable owner must fall back."""
        with self._lock:
            if self._settled.is_set():
                return
            self._accepted = False
            self._settled.set()

    def wait(self, within: Optional[float] = None) -> Optional[bool]:
        """`True` accepted, `False` refused, and `None` when the receipt did not arrive in time."""
        return self._accepted if self._settled.wait(within) else None


class Guidance(NamedTuple):
    """One live word and the durable inbound messages it accounts for, when there are any."""

    text: str
    messages: Tuple[int, ...] = ()
    conversation: int = 0
    admission: Optional[Admission] = None


def delegated_prompt(agent: str, conversation: int,
                     delegator: str) -> Tuple[str, Tuple[int, ...]]:
    """The pending delegated brief or guidance, oldest first and within the turn's bounds.

    Used both when the turn begins and while it runs. One selector for both moments means polling
    cannot reorder, clip, or claim a different set than the fallback turn would receive.
    """
    selected, used = [], 0
    for message, body in arriving.pending_from(
            agent, conversation, delegator, DELEGATED_MESSAGES_AT_MOST):
        cost = len(body.encode("utf-8")) + (2 if selected else 0)
        if selected and used + cost > DELEGATED_PROMPT_AT_MOST:
            break
        selected.append((message, body))
        used += cost
    return ("\n\n".join(body for _message, body in selected),
            tuple(message for message, _body in selected))


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

    def __init__(self, agent: str, conversation: int, turn: int,
                 caller_agent: Optional[str] = None) -> None:
        self.agent = agent
        self.conversation = conversation
        self.turn = turn
        #: Only delegated turns receive this. Person-facing turns are steered by their channel's
        #: in-process delivery and must not poll somebody else's durable messages.
        self.caller_agent = caller_agent
        self.watching = threading.Condition()
        self.words: List[Guidance] = []
        self._sent = set()
        self.open = True

    def say(self, word: str, messages: Tuple[int, ...] = (),
            admission: Optional[Admission] = None) -> bool:
        """Put one word in. **False when the turn will not read it** — and leave it pending.

        Durable messages are claimed while this turn is still provably open, under the same lock
        `close` needs. Once appended, `each` drains the word even if closing begins immediately.
        The provider feeder releases the claim if its stream has already stopped accepting input.
        """
        with self.watching:
            if not self.open:
                return False
            if messages:
                arriving.handled_by_turn(
                    self.agent, self.conversation, messages, self.turn)
            self.words.append(Guidance(word, messages, self.conversation, admission))
            self.watching.notify_all()
            return True

    def close(self) -> None:
        """No more words will be read. Said once the turn is over, and never taken back."""
        with self.watching:
            self.open = False
            self.watching.notify_all()

    def accepted(self, guidance: Guidance) -> None:
        """Remember that this exact durable batch crossed the provider's live input."""
        with self.watching:
            self._sent.update(guidance.messages)
        if guidance.messages:
            kept.add_turn_record(
                self.agent, self.turn, ADMITTED, {"messages": list(guidance.messages)})
        if guidance.admission is not None:
            guidance.admission.accepted()

    def refuse_unsent(self) -> None:
        """Close intake and return every claimed batch the provider did not accept.

        A provider can refuse the first batch while later batches are already queued. Releasing only
        the one in hand strands the rest on a turn that will never read them, so the queue is settled
        as one unit before the turn may become terminal.
        """
        with self.watching:
            self.open = False
            unsent = [guidance for guidance in self.words
                      if any(message not in self._sent for message in guidance.messages)]
            messages = tuple(dict.fromkeys(
                message for guidance in unsent for message in guidance.messages))
            self.watching.notify_all()
        try:
            if messages:
                arriving.released_by_turn(
                    self.agent, self.conversation, messages, self.turn)
        finally:
            for guidance in unsent:
                if guidance.admission is not None:
                    guidance.admission.refused()

    def each(self) -> Iterator[Guidance]:
        """Every word until intake closes, including durable A2A guidance written elsewhere."""
        at = 0
        while True:
            with self.watching:
                self.watching.wait_for(
                    lambda so_far=at: so_far < len(self.words) or not self.open,
                    timeout=GUIDANCE_EVERY if self.caller_agent else None)
                if at < len(self.words):
                    word, at = self.words[at], at + 1
                elif not self.open:
                    return
                else:
                    word = None
            if word is not None:
                yield word
                continue
            body, messages = delegated_prompt(
                self.agent, self.conversation, self.caller_agent or "")
            if not messages:
                continue
            try:
                self.say(body, messages)
            except records.Unreadable:
                # Another exact claimant won between the read and the claim. Read durable state
                # again rather than queueing a duplicate or treating somebody else's claim as loss.
                continue


#: The turns running right now that will still take a word, by the conversation each is running in.
#: **Only the ones that can be steered are here** — a turn whose brain reads nothing after its
#: prompt has nothing to publish, and offering one would let a caller believe a word landed.
#:
#: In memory and deliberately: this answers *is there a turn in this process to speak to*, and a
#: turn in another process is not one, however it was written down. What crosses processes is the
#: lock, which is the kernel's and is what `busy` asks.
_speaking_to: Dict[tuple, Words] = {}
_speaking_to_lock = threading.Lock()


#: The brains running right now **in this process**, by the conversation each is answering. What
#: `stop` reaches for, and the reason it is a registry rather than a pid written down: a pid in a
#: file is a number that gets reused, and the one thing that must never happen here is somebody
#: pressing `/stop` and signalling a stranger's program.
#:
#: In memory for the same reason `_speaking_to` is, and with the same consequence: a **scheduled**
#: turn runs in a process of its own and is not in here, so stopping one is not something this
#: answers. That is the honest boundary rather than a gap — a person pressing `/stop` in a
#: conversation is stopping the turn they are watching, and that turn is this process's.
class Ours:
    """One turn this process is running, and whether somebody has asked for it to end.

    **A holder rather than the brain itself, because the claim is taken before the brain exists.**
    A turn resolves a provider, builds its instructions and writes itself down before anything is
    started — a second or so on a cold agent — and a `/stop` pressed in that window found nothing to
    signal and told the person, truthfully but uselessly, that this was not a turn it could stop.
    So the turn is published the moment it is claimed, the brain is filled in when it starts, and a
    stop asked for in between is *remembered* and acted on the instant there is something to act on.
    """

    def __init__(self) -> None:
        self.stream: Optional["streaming.Stream"] = None
        self.asked = False
        self.ended = threading.Event()
        # A channel can observe the kernel claim before provider setup has decided whether this
        # turn accepts live guidance. Publish that decision explicitly so a follow-up does not race
        # the short gap and incorrectly start a fallback turn.
        self.reachability_known = threading.Event()
        self.reachable: Optional["Words"] = None
        self.forget_session = False

    def ends(self) -> None:
        """Stop the brain now, or as soon as there is one. Safe to call more than once."""
        self.asked = True
        if self.stream is not None:
            with contextlib.suppress(Exception):
                self.stream.stop()

    def began(self, stream: "streaming.Stream") -> None:
        """The brain is up. If a stop was asked for while it was starting, it goes straight away."""
        self.stream = stream
        if self.asked:
            with contextlib.suppress(Exception):
                stream.stop()

    def can_reach(self, words: Optional["Words"]) -> None:
        """Publish the turn's live-guidance queue, including the deliberate absence of one."""
        self.reachable = words
        self.reachability_known.set()


_running: Dict[tuple, Ours] = {}
_running_lock = threading.Lock()


def stop(agent: str, conversation: int) -> bool:
    """End the turn running in this conversation. `False` when there was none of ours to end.

    **The brain and everything it started.** `Stream.stop` signals the process *group*, which is
    what makes this honest: a brain runs editors, search tools and language servers, and signalling
    only the child we can see would leave every one of them behind, still working, on a turn
    somebody has been told is over.

    What becomes of the turn is not decided here and deliberately. The brain goes, its stream ends
    with no `done` on it, and `_became` reads that as a turn nobody could call finished — `STOPPED`,
    which is the word the surface renders as ✋. So the account of a stopped turn is written by the
    same code that writes every other one, and there is no second path that could disagree with it.
    """
    with _running_lock:
        running = _running.get((agent, conversation))
    if running is None:
        return False
    running.ends()
    return True


def stop_or_settle_pending(agent: str, conversation: int,
                           inbound_messages: Tuple[int, ...],
                           provider_name: Optional[str] = None,
                           provider_alias: Optional[str] = None,
                           model_name: Optional[str] = None) -> bool:
    """Stop a live turn, or make an unstarted inbound delegation terminal without a provider.

    The conversation claim closes the race with the worker thread a previous gateway beat may have
    spawned. If that worker owns the claim but has not published itself in `_running` yet, `Busy`
    leaves the durable stop request for the next beat instead of inventing a second turn.
    """
    if stop(agent, conversation):
        return True
    if not inbound_messages:
        return False
    try:
        with claiming(agent, conversation):
            settled = records.read(directory.records(agent))
            turn = kept.add_turn(agent, {
                "conversation_id": conversation,
                "provider_name": (provider_name if provider_name is not None
                                  else str(settled.get("provider_name") or "")),
                "provider_alias": (provider_alias if provider_name is not None
                                   else settled.get("provider_alias")),
                # No brain runs on this row, so nothing will ever report a model for it. What it was
                # admitted with is the whole of what it can say.
                "model_name": model_name,
                "admitted_model_name": model_name,
                "access_mode": protocol.ACCESS_WORK,
            })
            try:
                arriving.handled_by_turn(agent, conversation, inbound_messages, turn)
                kept.add_turn_record(
                    agent, turn, ADMITTED, {"messages": list(inbound_messages)})
            finally:
                kept.finish_turn(
                    agent, turn, kept.STOPPED,
                    {"failure_code": protocol.CANCELLED,
                     "failure_message": "this delegated work was stopped before it began"})
            return True
    except Busy:
        # `claiming` precedes `_stoppable` by only the publication window. Reach once more now; if
        # it is still between those two points, the durable row makes the next beat retry.
        return stop(agent, conversation)


@contextlib.contextmanager
def _stoppable(agent: str, conversation: int) -> Iterator[Ours]:
    """Publish this turn as one this process can end, for exactly as long as that is true.

    Taken out in a `finally` and only if it is still ours, which is the same care `_reachable`
    takes: a turn that finished while somebody was pressing `/stop` must not have the *next* turn
    in that conversation stopped by an entry it left behind.
    """
    ours = Ours()
    with _running_lock:
        _running[(agent, conversation)] = ours
    try:
        yield ours
    finally:
        ours.reachability_known.set()
        with _running_lock:
            if _running.get((agent, conversation)) is ours:
                del _running[(agent, conversation)]
        ours.ended.set()


def running_here(agent: str, conversation: int) -> bool:
    """Whether this process owns the turn, rather than merely observing an inherited lock."""
    with _running_lock:
        return (agent, conversation) in _running


def forget_when_done(agent: str, conversation: int) -> bool:
    """Forget sessions without a live turn being able to restore one across the decision."""
    with _running_lock:
        ours = _running.get((agent, conversation))
        if ours is not None:
            ours.forget_session = True
        # Settlement saves under this same lock. Whichever wins, `/new` is final: it either marks
        # first and no save happens, or waits for the save already underway and removes it.
        kept.forget_sessions(agent, conversation)
        return ours is not None


def stopping(agent: str, within: float) -> None:
    """Stop and wait for every provider turn this gateway owns, inside one shared budget."""
    with _running_lock:
        running = [one for (owner, _conversation), one in _running.items() if owner == agent]
    for one in running:
        one.ends()
    deadline = time.monotonic() + max(0.0, within)
    for one in running:
        one.ended.wait(max(0.0, deadline - time.monotonic()))


def settle_abandoned(agent: str) -> int:
    """Settle unfinished rows once the kernel proves no provider still owns their conversation."""
    settled = 0
    for row in kept.list_unfinished_turns(agent):
        if standing(agent, int(row["conversation_id"])) is not False:
            continue
        kept.finish_turn(
            agent, int(row["id"]), kept.STOPPED,
            {"failure_code": protocol.CANCELLED,
             "failure_message": "the gateway ended before this turn settled"})
        settled += 1
    return settled


def also_say(agent: str, conversation: int, word: str,
             messages: Tuple[int, ...] = (),
             admission: Optional[Admission] = None) -> bool:
    """Put a word into the turn already running in this conversation. **False if none took it.**

    False has three causes and one meaning. There may be no turn running here; there may be one
    whose brain cannot be steered; or there may have been one a moment ago that has since settled.
    All three mean the same thing to whoever is holding the word — **nobody is going to read it, so
    it is still yours** — and a caller that treated any of them as delivery would drop a message
    somebody sent.
    """
    # The process owns its turn from claim onward, while `_reachable` is necessarily published
    # only after provider capabilities and instructions are resolved. Wait for that decision when
    # it is ours; otherwise a follow-up arriving in this window is falsely treated as unsteerable.
    with _running_lock:
        ours = _running.get((agent, conversation))
    if ours is not None:
        ours.reachability_known.wait()
        speaking = ours.reachable
    else:
        with _speaking_to_lock:
            speaking = _speaking_to.get((agent, conversation))
    return bool(speaking and speaking.say(word, messages, admission))


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
        saying: Optional[Iterable[str]] = None,
        admitted: Optional[Callable[[], None]] = None,
        waiting: bool = False) -> Outcome:
    """Run one turn and write down everything about it. **The claim is taken here.**

    `watching` is handed every record the brain reported, as it arrives. `saying` is words to put
    into a turn already running, and reaches a brain only if that brain said it can be steered.

    A caller that passes no `saying` still gets a steerable turn published to `also_say`, so a
    message arriving on a channel mid-turn reaches the brain that is working on it. A caller that
    passes its own — the terminal, which has somebody typing — keeps it and is not published.
    """
    with claiming(request.agent, request.conversation, waiting=waiting) as held:
        # **Published as ours from the moment the claim is taken, not from when the brain starts.**
        # Resolving a provider and composing instructions is a second or so on a cold agent, and a
        # `/stop` pressed in that window found nothing to signal.
        with _stoppable(request.agent, request.conversation) as ours:
            return _held(request, held, watching, saying, ours, admitted)


def run_if(request: Request, admitting: Callable[[], bool],
           watching: Optional[Callable[[Dict[str, Any]], None]] = None,
           admitted: Optional[Callable[[], None]] = None) -> Optional[Outcome]:
    """Run only when ``admitting`` still accepts the origin under the conversation claim.

    The claim closes the newer-owner race: a platform message may be recorded before this wins and
    is then visible to ``admitting``; after this wins it belongs to the continuation turn's normal
    live-steering boundary. The callback is the durable once-only transition, not a preliminary
    question with a gap after it.
    """
    with claiming(request.agent, request.conversation) as held:
        if not admitting():
            return None
        with _stoppable(request.agent, request.conversation) as ours:
            return _held(request, held, watching, None, ours, admitted)


def _held(request: Request, held: int, watching, saying,
          ours: Optional[Ours] = None,
          admitted: Optional[Callable[[], None]] = None) -> Outcome:
    """One turn, with the conversation already claimed."""
    agent = request.agent
    admitted_turn = _admit(request)
    (_settled, provider_name, provider_alias, account_home, settings, effective_model, can,
     teammates, skill_names, prompt, resume, began, turn) = admitted_turn

    with _settled_whatever_happens(agent, turn) as settling:
        arriving.handled_by_turn(agent, request.conversation, request.inbound_messages, turn)
        if request.inbound_messages:
            kept.add_turn_record(
                agent, turn, ADMITTED, {"messages": list(request.inbound_messages)})
        if admitted is not None:
            with contextlib.suppress(Exception):
                admitted()
        kept.add_turn_record(agent, turn, INSTRUCTIONS, {
            "sha256": prompt.sha256,
            "layers": [{"name": one.name, "bytes": one.bytes_used} for one in prompt.layers],
            # The standing team and skill grants are volatile. Keep compact snapshots so a
            # historical instruction view can recompose the words this turn actually saw.
            "team": teammates,
            "skill_names": skill_names,
        })
        raw = adapters.raw_of(agent, request.conversation)
        began_at = _how_big(raw)
        told = environment.for_turn(
            agent=agent, home=directory.home(agent),
            provider_home=adapters.home(agent, provider_name),
            skills=grants.where(agent), turn=turn, access_mode=request.access_mode,
            raw=raw, model=effective_model, resume=resume,
            settings=settings, answering=request.answering,
            preface=prompt.text, owners=environment.owners_own(),
            provider_alias=provider_alias, provider_account_home=account_home)
        # **A turn nobody passed words to is still one a channel can speak into.** The words go
        # somewhere `also_say` can reach for exactly as long as this turn will read them.
        reachable = (Words(
            agent, request.conversation, turn,
            caller_agent=(request.caller_agent
                          if request.situation == instructions.AGENT_TO_AGENT else None))
                     if can["steer"] and saying is None else None)
        if ours is not None:
            ours.can_reach(reachable)
        # A provider may invoke `rundesk messages` to recover context during this turn. SQLite's
        # WAL reader needs the shared-memory sibling; some provider sandboxes may read the agent
        # directory but not create that file. Holding one gateway reader keeps the sidecars alive
        # for the documented child command, and the context managers close both on every path.
        with records.reading(directory.records(agent)):
            with _reachable(agent, request.conversation, reachable):
                said, stream = _the_brain(
                    request, provider_name, told, turn, held, can, watching,
                    saying if saying is not None else (reachable.each() if reachable else None),
                    reachable, ours)
        settling.update(_became(
            request, turn, said, stream, can, provider_name,
            began_at, _how_big(raw), time.monotonic() - began, ours=ours,
            provider_alias=provider_alias))
    return settling.outcome


def _admit(request: Request) -> _TurnAdmission:
    """Resolve and record a turn without an account change crossing its admission boundary."""
    agent = request.agent
    with locking.only_one(paths.lock(), "this install"):
        # **Resolved before anything is written down.** A provider nothing stands behind is a turn
        # that cannot start, and a row claiming admission would record something that never was.
        settled = records.read(directory.records(agent))
        configured_provider = str(settled.get("provider_name") or "")
        configured_alias = settled.get("provider_alias")
        provider_name = (request.provider_name if request.provider_name is not None
                         else configured_provider)
        adapters.where(provider_name)
        provider_alias = (request.provider_alias if request.provider_name is not None
                          else configured_alias)
        try:
            account_home = accounts.account_home(provider_name, provider_alias)
        except accounts.Refused as why:
            raise NotRunnable(str(why)) from why
        settings = (_as_settings(settled.get("agent_settings"))
                    if request.provider_name is None or provider_name == configured_provider
                    else None)
        effective_model = request.model_name
        if effective_model is None and request.provider_name is None:
            effective_model = settled.get("model_name")
        can = protocol.parse_capabilities(adapters.capabilities(provider_name, settings))
        if provider_alias is not None and not can.get("account_aliases"):
            raise NotRunnable(f"the {provider_name} adapter does not support account aliases")

        may_hand_off = (request.situation == instructions.USER_TO_AGENT
                        and request.access_mode != protocol.ACCESS_READ)
        teammates = team.for_agent(agent) if may_hand_off else ""
        skill_names = _skill_names(agent)
        prompt = instructions.build(situation=request.situation,
                                    variables=_about(request, provider_name, skill_names),
                                    additions=request.additions, team=teammates)
        resume = (None if request.fresh else kept.get_session(
            agent, request.conversation, provider_name, provider_alias))
        if request.lifecycle_continuation:
            safe_resume = bool(
                resume and can.get("resume") is True
                and provider_name == request.expected_provider
                and provider_alias == request.expected_provider_alias
                and prompt.sha256 == request.expected_instructions
                and kept.latest_instructions(
                    agent, request.conversation, provider_name,
                    provider_alias) == request.expected_instructions)
            if not safe_resume:
                if resume:
                    kept.delete_session(agent, request.conversation, provider_name, provider_alias)
                resume = None
        if (resume and kept.latest_instructions(
                agent, request.conversation, provider_name, provider_alias) != prompt.sha256):
            kept.delete_session(agent, request.conversation, provider_name, provider_alias)
            resume = None

        began = time.monotonic()
        turn = kept.add_turn(agent, {
            "conversation_id": request.conversation,
            "schedule_id": request.schedule_id,
            "schedule_name": _schedule_name(request) or None,
            # Requested spelling remains durable provenance; only account lookup/session identity
            # canonicalize a path adapter.
            "provider_name": provider_name,
            "provider_alias": provider_alias,
            # **What was actually selected, and it is the value the adapter is handed.** This wrote
            # `request.model_name` instead, so a turn running on the agent's configured model
            # recorded none at all and the ledger could not say which model an agent runs on.
            # `model_name` is the best-known answer and settlement may replace it with the one the
            # brain reports; `admitted_model_name` is this fact and nothing overwrites it.
            "model_name": effective_model,
            "admitted_model_name": effective_model,
            "access_mode": request.access_mode,
            "provider_capabilities": json.dumps(can, sort_keys=True),
            "session_resumed": 1 if resume else 0,
            "instructions_sha256": prompt.sha256,
            "instructions_bytes": prompt.total_bytes,
        })
        return _TurnAdmission(
            settled, provider_name, provider_alias, account_home, settings, effective_model, can,
            teammates, skill_names, prompt, resume, began, turn)


def admitted_message(agent: str, turn: int, message: int) -> bool:
    """Whether one durable message crossed this turn's admission boundary."""
    for record in kept.list_turn_records(agent, turn):
        if record["record_type"] != ADMITTED:
            continue
        try:
            messages = json.loads(record["event_data"] or "{}").get("messages", [])
        except (TypeError, ValueError):
            continue
        if message in messages:
            return True
    return False


def _the_brain(request: Request, provider_name: str, told: Dict[str, str], turn: int, held: int,
               can: Dict[str, bool], watching, saying,
               reachable: Optional[Words] = None,
               ours: Optional[Ours] = None) -> Tuple[List[Dict[str, Any]], Any]:
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
            speaking = _speaking(agent, turn, stream, saying, reachable=reachable)
        else:
            # Told there is no more coming, so a brain that reads its input to the end can answer.
            stream.say(request.prompt)
            stream.no_more()
        if ours is not None:
            # The brain is up, so what a stop would signal now exists. A stop asked for while it was
            # starting is remembered by the holder and takes effect here, on this line.
            ours.began(stream)
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
            if reachable is not None:
                # The turn cannot become terminal while durable guidance is still claimed but
                # neither sent nor released. The feeder owns that settlement boundary, so teardown
                # waits for it rather than letting collection race ahead.
                speaking.join()
            else:
                # An attended caller owns this iterator: terminal stdin may remain open after the
                # provider has emitted `done` and exited. Rundesk cannot close it and must not make
                # provider settlement wait forever for somebody to type another word.
                speaking.join(timeout=1.0)
        stream.stop()
    return said, stream


def _speaking(agent: str, turn: int, stream, saying,
              reachable: Optional[Words] = None) -> Optional[threading.Thread]:
    """Put words into a turn that is already running, from a thread of its own.

    On its own thread because the caller's is draining records: a person typing and a brain talking
    happen at the same time, and a turn that could only do one of them at once would deadlock the
    first time somebody interrupted it.

    **Nothing that goes wrong in here is allowed to be silent.** A thread whose exception nobody
    retrieves failed invisibly, so a word that could not be said is written into the account as
    `UNSENT` rather than leaving the turn reporting that it was fine.

    **`UNSENT` and never `LOST`.** A brain that finished while somebody was still typing is an
    ordinary race with an ordinary answer — the word stays durable for the next turn — and counting
    it as a record that never arrived sent people looking for a vendor that had not moved.
    """
    if saying is None:
        return None

    def speak() -> None:
        guidance = Guidance("")
        try:
            for received in saying:
                guidance = (received if isinstance(received, Guidance)
                            else Guidance(str(received)))
                kept.add_turn_record(agent, turn, SENT,
                                     _bounded({"text": guidance.text, "mid_turn": True}))
                accepted = stream.say(protocol.build_say_line(
                    guidance.text, protocol.STEERING_CONTEXT))
                if not accepted:
                    if reachable is not None:
                        reachable.refuse_unsent()
                    elif guidance.messages:
                        arriving.released_by_turn(
                            agent, guidance.conversation, guidance.messages, turn)
                    kept.add_turn_record(agent, turn, UNSENT,
                                         {"unsent_count": 1,
                                          "reason": "it had already finished"})
                    return
                if reachable is not None:
                    reachable.accepted(guidance)
        except Exception as why:                       # noqa: BLE001 — see the docstring
            if reachable is not None:
                with contextlib.suppress(Exception):
                    reachable.refuse_unsent()
            elif guidance.messages:
                with contextlib.suppress(Exception):
                    arriving.released_by_turn(
                        agent, guidance.conversation, guidance.messages, turn)
            with contextlib.suppress(Exception):
                kept.add_turn_record(agent, turn, UNSENT,
                                     {"unsent_count": 1, "reason": f"not said: {why}"})
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
        _written_down(agent, turn, LOST, {"lost_count": one.lost_count, "reason": one.reason})
        return
    record = protocol.parse_record(one)
    if record is None:
        _written_down(agent, turn, UNKNOWN, {}, raw_line=str(one)[:AN_EVENT_AT_MOST])
        return
    said.append(record)
    if record["type"] not in ("text",):
        # `text` is gathered and written as one message at the end: a row per fragment is a history
        # nobody can read back and a search that matches half a sentence.
        _written_down(agent, turn, record["type"], _bounded(record))
    if watching is not None:
        with contextlib.suppress(Exception):
            watching(record)


def _written_down(agent: str, turn: int, kind: str, values: Dict[str, Any],
                  raw_line: Optional[str] = None) -> None:
    """One diagnostic row kept — and **the turn carried on when it cannot be.**

    `_heard` says it never raises and did. `kept.add_turn_record` opens a write transaction of its
    own for every record off the brain, so a store that will not take one — contention outlasting
    the retries in `records._begun`, a disk that filled, a file made unwritable — threw straight out
    of the loop reading the stream.

    **What that cost was never the row it failed on.** `_became` never ran, so the brain's answer
    was not written to `conversation_messages`, the resume handle was dropped, and a turn that had
    worked settled as `stopped` — on a channel, reported to the person as "I could not answer that".
    Measured: a store made unwritable mid-stream lost a finished answer and left the turn unsettled.

    So the cheapest thing in the turn is the thing that gives way. The row is noted as missing and
    the answer survives, which is the opposite of the trade that was being made.
    """
    try:
        kept.add_turn_record(agent, turn, kind, values, raw_line=raw_line)
    except (kept.Refused, records.NotThere, records.Unreadable, sqlite3.DatabaseError,
            OSError) as why:
        note(agent, f"turn {turn}: a {kind} record could not be kept ({why})", logs.WARNING)


def _became(request: Request, turn: int, said: List[Dict[str, Any]], stream,
            can: Dict[str, bool], provider_name: str, began_at: int, ended_at: int,
            elapsed: Optional[float] = None, ours: Optional[Ours] = None,
            provider_alias: Optional[str] = None) -> Dict[str, Any]:
    """What this turn came to, and everything the records keep about it."""
    agent = request.agent
    # An attended outcome keeps everything the brain said for its live caller. An unattended
    # schedule or delegation has one report: activity may exist in its stream, but only the last
    # complete response is what its owner or calling agent receives. Channel history keeps ordinary
    # remarks below while removing only explicit finals that later guidance superseded.
    unattended = request.situation in (instructions.SCHEDULE_TO_AGENT,
                                       instructions.AGENT_TO_AGENT)
    closing = protocol.last_thought(said)
    reply = closing if unattended else protocol.reply(said)
    answered = bool(reply.strip()) if unattended else protocol.has_answer(said)
    brain_said = protocol.brain_said_ok(said)
    gone = stream.outcome()
    used = protocol.usage_of(said)

    # An explicit final produced before later guidance is superseded, not a second answer. Preserve
    # every ordinary remark in channel history and remove only earlier explicit finals; narrowing
    # all channel history to the closing thought would silently discard useful working context.
    remembered = reply
    explicit = [one for one in said
                if one.get("type") == "text" and one.get("final") is True]
    if request.source == arriving.FROM_CHANNEL and len(explicit) > 1:
        last_final = explicit[-1]
        remembered = protocol.reply(
            one for one in said if one.get("final") is not True or one is last_final)
    if remembered.strip():
        arriving.said_by_agent_into(agent, request.conversation, remembered, turn=turn)
    handle = protocol.resume_handle(said)
    if handle and can["resume"]:
        if ours is None:
            kept.save_session(agent, request.conversation, provider_name, handle, provider_alias)
        else:
            with _running_lock:
                if not ours.forget_session:
                    kept.save_session(
                        agent, request.conversation, provider_name, handle, provider_alias)

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
    elif brain_said is False:
        status = kept.FAILED
    elif brain_said is True and (code is not None or message is not None):
        # **A reason for failing belongs on a `done` that says `ok: false`, and nowhere else.** The
        # brain is the one thing that knows whether its turn worked, so anything arriving beside its
        # own `ok: true` is an adapter breaking the contract — and read as a failure it inverts the
        # answer: measured, an owner was told `FAILED — it did not answer` on the line above the
        # answer it gave, and the ledger agreed. It is dropped rather than acted on, and the adapter
        # is named in the log, because this is the adapter's defect to fix.
        #
        # **Both fields, not only the word.** `protocol.failure_code` answers `None` for a word this
        # release does not know as well as for one that was never sent, so an adapter contradicting
        # itself in prose alone — or with a word rundesk dropped — would otherwise leave a reason
        # for failing sitting on a turn recorded as done.
        note(agent, f"turn {turn}: the adapter reported {code or message!r} on a turn it said "
                    "worked, so it was dropped — a reason for failing belongs on a done that is "
                    "not ok", logs.WARNING)
        code, message = None, None
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
                           last_thought=closing, failure_code=code,
                           failure_message=message, usage=used,
                           files=tuple(protocol.file_records(said)),
                           provider_name=provider_name, provider_alias=provider_alias,
                           elapsed_seconds=elapsed),
        "values": {
            "exit_code": gone.code,
            "failure_code": code,
            "failure_message": (message or "")[:AN_EVENT_AT_MOST] or None,
            # **The model that answered, and it is a different fact from the one asked for.**
            # Written at settlement because only the brain knows which one really ran, and left
            # alone when it named none — so `model_name` stays the best-known answer rather than
            # being emptied by a brain that stayed quiet, and `reported_model_name` says whether a
            # brain named one at all. A row with neither is a row an older release wrote.
            **({"model_name": used.model_name,
                "reported_model_name": used.model_name} if used.model_name else {}),
            "usage_reported": 1 if used.usage_reported else 0,
            "input_tokens": used.input_tokens, "output_tokens": used.output_tokens,
            "cache_read_tokens": used.cache_read_tokens,
            "cache_write_tokens": used.cache_write_tokens,
            "context_tokens": used.context_tokens,
            # The three drift counters are deliberately absent: each is kept by the insert that
            # causes it, so a record written after this runs is still counted. See `kept.SETTLED`.
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

    **Swallowed is not unrecorded.** A settlement that never landed leaves the row saying `working`
    for ever, and `commands/turns` will rightly show it as abandoned — but nothing said why, so the
    one failure this whole block exists to survive was also the one nobody could see afterwards.
    `note` is used rather than a raise because it cannot fail: it swallows its own trouble, which is
    what makes it safe to call from a process on the way down.
    """
    settling = _Settling()
    try:
        yield settling
    finally:
        try:
            if settling.outcome is None:
                kept.finish_turn(agent, turn, kept.STOPPED,
                                 {"failure_code": protocol.CANCELLED,
                                  "failure_message": "this turn was stopped before it settled"})
            else:
                kept.finish_turn(agent, turn, settling.outcome.turn_status, settling.values)
        except Exception as why:                   # noqa: BLE001 — see the docstring
            note(agent, f"turn {turn}: it could not be settled, so it stays working ({why})",
                 logs.WARNING)


def _about(request: Request, provider_name: str,
           skill_names: Optional[str] = None) -> Dict[str, object]:
    """The variables a layer may read, for this turn."""
    return {
        "agent_name": request.agent,
        "agent_home": str(directory.home(request.agent)),
        "provider_name": provider_name,
        "access_mode": request.access_mode,
        "schedule_name": _schedule_name(request),
        "conversation_id": request.conversation,
        "source_kind": request.source,
        "audience_id": request.place or request.agent,
        "caller_agent": request.caller_agent,
        "skill_names": _skill_names(request.agent) if skill_names is None else skill_names,
    }


def _skill_names(agent: str) -> str:
    """The active granted skill names, in the same order the runtime exposes them."""
    try:
        return ", ".join(one.name for one in grants.held(agent)) or "none"
    except OSError:
        return "unavailable"


def _schedule_name(request: Request) -> str:
    """What the schedule that caused this turn is called, and nothing when no schedule did.

    **The schedule's name, and nothing else's.** `place` is a Discord room on a channel turn and the
    agent's own name at a terminal, so putting either behind a name like this is a value that is
    wrong the day a layer starts reading it.

    Derived in one place because it is now read twice: the layers are handed it for this turn, and
    the turn's own row keeps it so the ledger still says which schedule ran once that schedule has
    been taken away. Two derivations of one fact are two things that can come to disagree.
    """
    return request.schedule_name or (request.place if request.schedule_id else "")


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
