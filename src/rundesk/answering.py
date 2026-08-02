"""What arrives on a channel, carried through to an answer.

The only module that knows `channel`, `turn` and `agent` all exist — the mirror
of what `turn` is for a brain. The shape, in the order it happens:

    somebody spoke -> may they? -> admit a turn -> say it is taken up
                   -> show what the agent did, while it does it
                   -> hand over the answer, whole, once
                   -> say how it ended

**Authorization is here and never in the adapter (R-CH-4).** An adapter reports who spoke;
whether that person may be answered is decided against the record the owner wrote. An
adapter that filtered for itself would be one whose author could get it wrong, on a machine
where the agent runs tools — so a stranger's adapter is safe because of where this decision
lives rather than because of how carefully it was written.

**The turn's lifecycle is here and never in the adapter (R-CAD-3).** Five states, decided
once. An adapter working out for itself when a message had been seen would be
re-implementing the turn, and two surfaces would eventually disagree about the same run
with its own account matching neither.

**Nothing here writes anything down.** The run's account already records what was asked,
what the brain did and what it cost, keyed by the run. A channel adds delivery on top of
that and must never become the only place something was written (R-CH-15).
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from rundesk import agent as agents
from rundesk import channel, migration, provider, store, turn

#: How many messages may be waiting for a conversation whose brain cannot be steered.
#: Small on purpose: somebody typing while an agent works is answering the conversation,
#: not queueing a batch of work, and an unbounded queue is a way to hand one person the
#: whole gateway. Past it the oldest waiting message goes and is said to have.
WAITING = 4

#: How many times a shutdown looks again for work that appeared while it was cancelling.
#: More than one because ending a turn is what starts the next, and a small number
#: because nothing here starts work forever — `_stopping` is what actually ends it, and
#: this only has to outlast the tasks already in flight when it was set.
_UNWINDING = 3

#: How many conversations to keep hold of. A channel is held open for weeks and every
#: distinct conversation it has ever seen had an entry that nothing ever removed — a
#: thread opened once in March still had one in July. What is kept for a conversation is
#: only what a turn running in it needs, so the ones to drop are the ones with nothing
#: running: where a conversation *got to* is in the agent's own record and is found again
#: by name, so forgetting one here costs nothing at all.
CONVERSATIONS = 200

# A recovery continues the provider session; it never replays the person's original prompt,
# because doing so can repeat tool effects that already happened before the restart.
CONTINUE = (
    "Continue the interrupted work from where the previous gateway stopped. "
    "Do not repeat actions already completed. Finish the original request."
)

AFTER_UPDATE = (
    "The external Rundesk update attempt has finished and the gateway is back online. "
    "Verify the installed version and update outcome, then continue and finish the user's "
    "original request. Do not stop at reporting status or repeat completed actions."
)

# What a named agent is woken with when work it handed to a role has reported back
# (R-ROL-15). Rundesk states what it mechanically knows and asks for a review; it
# never says the work succeeded, because whether it did is exactly what the review is for
# and Rundesk read nothing out of the worker's report to find out (R-ROL-16).
REVIEW_HANDOFF = """Work you handed to a role has finished and reported back. Nobody has been told anything about it yet, and this report has not been checked.

{handoff}

Review it: verify the claims that matter against the work itself rather than accepting them, then answer the person who asked in this conversation. Say what you checked. If the report is wrong or incomplete, say so and what you are doing about it. Do not start another role run from this turn."""

# Any absolute local Markdown link is delivery intent (R-CH-31). The optional reserved
# prefix remains portable across brains; prefix that form or the opening bracket with a
# backslash when showing one literally. The parser below handles balanced brackets and
# parentheses because both are valid filename characters and regex cannot balance them.
_LOCAL_ATTACHMENT_START = re.compile(r"(?<!\\)(?:rundesk-attach:[ \t]+)?\[")


@dataclass
class Waiting:
    """A follow-up retained until a running brain actually accepts it."""

    text: str
    user: str
    ref: str | None
    preface: str


class Exchange:
    """One conversation, and the turn running in it if there is one."""

    def __init__(self, conversation: str):
        self.conversation = conversation
        self.run: str | None = None
        self.ref: str | None = None
        self.task: asyncio.Task | None = None
        self.can: dict = {}
        #: What has been said to a running turn that can take it, and what is waiting for
        #: one that cannot. Two different things, deliberately: one reaches the brain now
        #: and the other becomes its own turn later.
        #: Complete things the brain has said in this turn, in order. Each is shown as
        #: the next one arrives, so the one still in hand at the end is the answer — the
        #: last thing it said is the thing somebody replies to, and it is only knowable
        #: as the last once the turn is over.
        self.spoken: list = []
        self.saying: asyncio.Queue | None = None
        self.waiting: list = []
        self.stopped = False
        #: Somebody asked for this conversation to start fresh while a turn was running
        #: in it. The turn is left to finish, what it learned is not kept, and later words
        #: wait for the next turn rather than steering the old provider.
        self.forgotten = False


class Answering:
    """One channel's worth of conversations, and the turns running in them.

    Everything it needs to reach the world is passed in: `sending` is how a record reaches
    the adapter, and `carry` is what runs a turn. Both are arguments so the whole of this
    is exercised with no adapter, no brain and no network anywhere near it.
    """

    def __init__(self, name: str, channel_name: str, record: dict, sending,
                 where=None, carry=None, note=None, restarting=None, querying=None,
                 restart_waiting=None, restart_ready=None):
        self.name = name
        self.channel = channel_name
        self.record = record
        self._sending = sending
        self._where = where
        self._carry = carry if carry is not None else turn.carry
        self._note = note if note is not None else (lambda said: None)
        #: How to ask for the agent to be cycled. An argument, because what
        #: keeps a gateway up is the machine's and this file has never heard
        #: of a gateway (R-CH-16).
        self._restarting = restarting
        self._restart_waiting = restart_waiting or (lambda _run: False)
        self._restart_ready = restart_ready or (lambda _run: None)
        #: Read-only gateway facts, resolved above this layer. Answering owns the
        #: authorization boundary but knows neither how an agent nor its gateway is
        #: represented (R-CAD-17).
        self._querying = querying
        self.exchanges: dict = {}
        self.connected = False
        #: Everything on its way to the adapter, in the order it was decided. One queue
        #: and one writer, because a mark saying a turn is finished must not overtake the
        #: answer it is finishing — and a record shown out of order is worse than one not
        #: shown at all, since a reader has no way to tell.
        self._showing: asyncio.Queue = asyncio.Queue()
        self._writer: asyncio.Task | None = None
        #: Set once this channel is going away. A turn ending schedules whatever was
        #: waiting behind it, and that happens *while* the shutdown is cancelling — so
        #: without this, cancelling the last turn started the next one, after the caller
        #: had been told everything had stopped (R-CH-11).
        self._stopping = False
        self._recovered = False

    # -- what the adapter says -------------------------------------------------------

    async def heard(self, said) -> None:
        """One record from the adapter, acted on or passed over.

        Anything unreadable, of a kind nobody knows, or missing what its kind means is
        already `None` by the time it gets here — the seam refuses it rather than letting
        a decision about what it meant be made further from the adapter that knows.
        """
        it = channel.understood(said) if not isinstance(said, dict) else said
        if it is None:
            return
        kind = it.get("type")
        if kind == "ready":
            self.connected = True
            self._note(f"channel '{self.channel}' is connected")
            await self._recover()
        elif kind == "gone":
            # Said, never acted on. Coming back is the adapter's own (R-CAD-7), and a
            # turn already running is not interrupted by the surface it will be shown on.
            self.connected = False
            self._note(f"channel '{self.channel}' lost its connection: {it.get('why') or 'no reason given'}")
        elif kind == "arrived":
            await self._arrived(it)
        elif kind == "control":
            await self._control(it)
        elif kind == "configure":
            await self._configure(it)
        elif kind == "query":
            await self._query(it)

    async def _arrived(self, it: dict) -> None:
        if not channel.allowed(self.record, it["user"]):
            # Silence, and never a refusal. Answering a stranger to tell them they are a
            # stranger confirms the agent is listening and spends the owner's tokens
            # doing it (R-CH-4).
            self._note(f"channel '{self.channel}': a message from someone not allowed was not dispatched")
            return
        brought = it.get(channel.ATTACHED) or []
        if brought:
            self._note(f"channel '{self.channel}': {len(brought)} attached, named to the agent")
        held = self.exchanges.get(it["conversation"])
        if held is None:
            self._make_room()
            held = self.exchanges.setdefault(it["conversation"], Exchange(it["conversation"]))
        if held.task is not None and not held.task.done():
            await self._while_running(held, it)
            return
        held.ref = it.get("ref")
        held.stopped = False
        held.task = asyncio.ensure_future(
            self._one(held, _asked(it), it["user"], self._from(it)))

    def _from(self, it: dict) -> str:
        """What this agent is told about the situation, before it reads the words
        (R-CH-21, R-CH-22, R-AGT-16, R-AGT-17, R-AGT-38).

        Rundesk's core and channel instructions come first. A channel or adapter may
        override only the channel layer or append to it; the agent owner's instructions
        always append and never displace either core layer.
        """
        return channel.preface(
            self.record, self.name, self.channel, it,
            core_variables=agents.instruction_variables(self.name, self._where),
            append=agents.added_instructions(self.name, self._where))

    #: What rundesk says on a surface when a scheduled run that will report there begins
    #: (R-SCH-46). Rundesk's own bookkeeping and never the agent's prose: an owner cannot
    #: otherwise tell that work started at six in the morning, and the first sign of it is
    #: a report arriving twenty minutes later beside answers to other questions, with
    #: nothing tying the two together.
    STARTING = "💻 Working on '{named}' — I will report back when it is done."

    async def told_a_schedule_started(self, named: str) -> tuple[bool, str | None]:
        """Say on this surface that one of this agent's schedules has begun (R-SCH-46).

        The sibling of `told_what_a_schedule_did`, and where it goes is resolved here **once
        for both** — the place the owner named, and the newest conversation on this surface
        only when they named none (R-SCH-32). Hands back whether anything went out and the
        conversation it went to, because the report is delivered *there* rather than asking
        the same question again twenty minutes later.

        Resolving the same way is not resolving to the same answer: the newest conversation
        is whichever room somebody last spoke in, and somebody speaking in another one is
        exactly what a long run gives them time to do. Re-derived at the end, the notice
        stands in one room for ever with nothing under it while the outcome lands in
        another, anchored to nothing — which is worse than neither message.

        **Only where a report is actually delivered.** Which schedules those are is not
        known here: a schedule that starts a program has no report to anchor, and only the
        gateway that started it knows which kind it was. So this is called for one kind and
        not the other rather than deciding for itself.

        **Nowhere to say it is nowhere to say it started.** A surface nobody has spoken on
        and no place named has no room for the notice either, and hands back that it said
        nothing — the caller owes a reply only to a notice that actually went out.

        **A place named is carried, not resolved for.** A word an owner said is what the
        adapter is handed for both messages, so the two reach the same room whether or not
        rundesk has ever seen it; there is nothing to carry over and nothing that can drift.

        **Not written down where it was delivered**, which is the one place this differs
        from the report. R-SCH-33 exists so a person replying to what the agent *said*
        reaches a brain whose session saw it; nobody replies "nice work" to rundesk saying
        work has begun, and writing it in would put a line the agent never said into the
        account of what it said.
        """
        kept = agents.reading(self.name, self._where)
        row = kept.schedule(named) or {}
        place = row.get("place")
        where_it_goes, said = self._where_to_say(kept, place)
        if where_it_goes is None and not place:
            self._note(f"channel '{self.channel}': nowhere to say that '{named}' has "
                       f"started — nothing has been said on this surface yet")
            return False, None
        # The schedule's name goes over with it, because that is what the surface holds the
        # posted message under and what the report names to find it again (R-DIS-30). The
        # surface is never asked to read it — it is a key, exactly as `place` is a word.
        self._tell(type="said", conversation=where_it_goes, place=place or None,
                   text=self.STARTING.format(named=named), schedule=named, began=True)
        if where_it_goes is None and said:
            self._note(said)
        return True, where_it_goes

    async def told_what_a_schedule_did(self, named: str, result, where=None) -> None:
        """Say on this surface what one of this agent's schedules came to (R-SCH-31).

        **The one thing here that nobody asked for.** Every other record this sends answers
        something that arrived; this one is the clock's work reaching the place its owner
        already looks, because work that failed at three in the morning is no use in an account
        nobody opens until they think to.

        **A turn's report is a completed answer** (R-SCH-50), with the provider, elapsed time,
        and usage its outcome carried. The clock supplied no inbound question, but the channel
        can still present the report like every other final answer and anchor it to the notice
        that the run started. Program and startup outcomes have no turn outcome to enrich, so
        those remain complete remarks.

        **Where** is the place the schedule named, and the newest conversation on this surface
        only when it named none. A channel reaching a whole server has many rooms, and picking
        whichever one somebody last spoke in is how a daily report lands somewhere nobody meant
        — so an owner says which, and the word they say is carried to the adapter unread
        (R-SCH-32). A surface nobody has ever spoken on and no place named has nowhere for this
        to go, and that is said rather than invented.

        **What is delivered is written down where it was delivered** (R-SCH-33). Without that,
        the next message in that conversation reaches a brain whose session never saw this, so
        somebody saying "nice work" about it is asking about something the agent has no record
        of having said there.

        **A reply to the notice that this run started, where one went out** (R-SCH-46). The
        schedule's name is on the record and the surface anchors to whatever it is holding
        under that name; a surface holding nothing posts it plainly, which is what every
        report did before there were notices at all.

        **`where` is where that notice went**, handed back when it went out and passed
        straight through here — the one thing this does not work out for itself. Asking
        again would ask a *different* question: the newest conversation is whichever room
        somebody last spoke in, and a run long enough to be worth announcing is long enough
        for that to have changed. A schedule that named a place carries the word instead,
        and one that never announced resolves where it always did.
        """
        kept = agents.reading(self.name, self._where)
        row = kept.schedule(named) or {}
        place = row.get("place")
        if where and not place:
            where_it_goes, said = where, ""
        else:
            where_it_goes, said = self._where_to_say(kept, place)
        if where_it_goes is None and not place:
            self._note(f"channel '{self.channel}': nowhere to say what '{named}' did — "
                       f"nothing has been said on this surface yet")
            return
        became = getattr(result, "became", result)
        text = self._what_it_did(kept, named, became)
        outcome_run = getattr(result, "run", None)
        run = kept.run(outcome_run) if isinstance(outcome_run, str) else None
        if run is None:
            ran = kept.runs(schedule_id=row.get("id"), limit=1)
            run = ran[0] if ran else None
        # The place goes over even when we resolved a conversation ourselves: only the adapter
        # can reach a room nobody has spoken in yet, and it is the one that knows what the word
        # means. A surface that cannot resolve one falls back to the conversation (R-CAD-16).
        if outcome_run is None:
            self._tell(type="said", conversation=where_it_goes, place=place or None,
                       text=text, schedule=named)
        else:
            # A scheduled turn is still a completed channel answer (R-SCH-50). Its outcome
            # is the only place the session-size figure survives: the durable run keeps the
            # billed pieces but deliberately does not store that provider snapshot.
            text, linked = _attachment_lines(text)
            attachments = await self._made([*linked, *getattr(result, "files", ())])
            tokens = getattr(result, "tokens", {})
            if isinstance(tokens, dict) and tokens.get("reported"):
                usage = {key: tokens[key]
                         for key in ("input", "output", "cached", "written", "session")
                         if isinstance(tokens.get(key), int)}
                self._tell(type="usage", conversation=where_it_goes,
                           run=outcome_run, schedule=named, **usage)
            final = {
                "type": "answer", "conversation": where_it_goes,
                "place": place or None, "run": outcome_run, "text": text,
                "schedule": named, "attachments": attachments,
            }
            if run is not None:
                final["provider"] = provider.label(run.get("provider") or "")
            elapsed = getattr(result, "elapsed", None)
            if isinstance(elapsed, (int, float)) and not isinstance(elapsed, bool):
                final["elapsed"] = elapsed
            allowed = self.record.get("allow")
            if (isinstance(allowed, list) and len(allowed) == 1
                    and isinstance(allowed[0], str) and allowed[0]):
                final["recipient"] = allowed[0]
            self._tell(**final)
        if where_it_goes is not None:
            kept.answered(where_it_goes, run["id"] if run else None,
                          store.stamped(), text)
        elif said:
            self._note(said)

    async def told_update_finished(self, conversation: str, text: str) -> None:
        """Deliver an update outcome and resume its work after reconnect (R-UPD-40, R-UPD-41)."""
        if not self.connected:
            raise RuntimeError(f"channel '{self.channel}' is not connected")
        await self._sending(channel.spoken(
            type="said", conversation=conversation, text=text,
        ))
        agents.records(self.name, self._where).answered(
            store.conversation_id(self.channel, conversation),
            None, store.stamped(), text,
        )
        held = self.exchanges.get(conversation)
        if held is not None and held.task is not None and not held.task.done():
            # A message that arrived during reconnect already continued this conversation.
            # Starting another turn would duplicate the work the owner just resumed.
            return
        if held is None:
            self._make_room()
            held = self.exchanges.setdefault(conversation, Exchange(conversation))
        began = asyncio.Event()
        held.ref = None
        held.stopped = False
        held.task = asyncio.ensure_future(
            self._one(
                held, AFTER_UPDATE, "", prompt_author="rundesk",
                on_admitted=lambda _run: began.set(),
            )
        )
        admitted = asyncio.ensure_future(began.wait())
        done, _pending = await asyncio.wait(
            {held.task, admitted}, return_when=asyncio.FIRST_COMPLETED
        )
        if began.is_set():
            admitted.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await admitted
            return
        admitted.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await admitted
        # A turn that failed before admission is not a continuation. Leave the update
        # request undelivered so the reconnected gateway tries again truthfully.
        await held.task
        raise RuntimeError("the post-update continuation was not admitted")

    async def told_role_finished(self, conversation: str, handoff: dict,
                                    reviewing=None) -> None:
        """Wake the named parent to review one role handoff (R-ROL-15).

        **Nothing is posted here.** The worker's report is not an answer and is not news:
        it is unchecked work, and a surface showing it would have delivered a result the
        named agent never reviewed — which is the one thing this whole path exists to
        prevent (R-ROL-16). What is posted is whatever the agent says after reading it.

        Raised rather than returned when the review cannot start, so the caller leaves it
        owing and tries again. A handoff quietly marked delivered because a room was busy
        is work that was done and nobody was ever told about.
        """
        if not self.connected:
            raise RuntimeError(f"channel '{self.channel}' is not connected")
        held = self.exchanges.get(conversation)
        if held is not None and held.task is not None and not held.task.done():
            # Somebody is already being answered in this room. Two turns in one
            # conversation are two brains on one session, and the review can wait.
            raise RuntimeError("the parent conversation is already answering somebody")
        if held is None:
            self._make_room()
            held = self.exchanges.setdefault(conversation, Exchange(conversation))
        began = asyncio.Event()
        held.ref = None
        held.stopped = False

        def admitted(run: str) -> None:
            # Written before the turn can ask for anything: which run is reviewing a
            # handoff is what refuses it a second role level, and a marker written
            # afterwards would be written after the moment it guards (R-ROL-13).
            if reviewing is not None:
                reviewing(run)
            began.set()

        held.task = asyncio.ensure_future(
            self._one(
                held, REVIEW_HANDOFF.format(handoff=_handoff_text(handoff)), "",
                prompt_author="rundesk", on_admitted=admitted,
            )
        )
        waiting = asyncio.ensure_future(began.wait())
        await asyncio.wait({held.task, waiting}, return_when=asyncio.FIRST_COMPLETED)
        waiting.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await waiting
        if began.is_set():
            return
        # A turn that failed before admission never read the handoff. Leave it owing.
        await held.task
        raise RuntimeError("the role review turn was not admitted")

    async def told_the_owner(self, text: str) -> None:
        """Say something to this agent's owner alone, wherever this surface reaches them
        (R-CH-32).

        **No conversation, on purpose.** This is rundesk's own bookkeeping about the agent
        rather than anything the agent said in a room, and where an owner is reached
        privately is the surface's own answer — a room, a thread and a direct message are
        one platform's words for a place, and this file has never heard of any of them
        (R-CAD-13). A surface with no private way to reach anybody shows nothing, which is
        the same freedom it has over everything else it is told.

        Not written into what the agent has said, for the reason the schedule notice is
        not: a brain that never wrote the line would find it in its own record and take it
        for something it had said.
        """
        if not self.connected:
            raise RuntimeError(f"channel '{self.channel}' is not connected")
        await self._sending(channel.spoken(type="owner-notice", text=text))

    async def told_restart_finished(self, conversation: str, text: str) -> None:
        """Deliver one queued restart outcome after reconnect (R-GW-43)."""
        if not self.connected:
            raise RuntimeError(f"channel '{self.channel}' is not connected")
        await self._sending(channel.spoken(
            type="said", conversation=conversation, text=text, continues=False,
        ))
        agents.records(self.name, self._where).answered(
            store.conversation_id(self.channel, conversation),
            None, store.stamped(), text,
        )

    def _where_to_say(self, kept, place):
        """The conversation to say it in, and why there is none where there is none.

        A place we have already seen is a conversation of ours. One we have not is the
        adapter's to resolve, so nothing here is refused for it — the record goes over with the
        place on it and no conversation, and a surface that can find the room says it there.
        """
        if place:
            for one in kept.conversations(channel=self.channel, limit=CONVERSATIONS):
                if one.get("space") == place:
                    return one["id"], ""
            return None, (f"channel '{self.channel}': nothing has been said in '{place}' yet, "
                          f"so it is left to the surface to find it")
        seen = kept.conversations(channel=self.channel, limit=1)
        return (seen[0]["id"] if seen else None), ""

    @staticmethod
    def _what_it_did(kept, named: str, became: str) -> str:
        """What the agent said, where it said anything — and what it came to where it did not.

        **The answer alone when there is one** (R-SCH-34). A person reading a room wants what
        their agent found, not a line of rundesk's bookkeeping in front of it: "schedule
        'nightly' finished" above the answer is scaffolding they did not ask for, on every post,
        for ever. Which schedule produced it is in the account and in `schedules`, where
        somebody asking that question is already looking.

        **What it came to, where that is all there is.** A schedule that started a *program* has
        no answer to read back, and one that failed has something a reader must not be left to
        infer from silence — so both still say what happened. One shape for every kind, decided
        here rather than by two callers.

        What it said is read out of the account rather than passed in, because the account is
        where it already is.
        """
        row = kept.schedule(named) or {}
        said = ""
        for run in kept.runs(schedule_id=row.get("id"), limit=1) if row.get("id") else []:
            said = "\n\n".join(
                one["text"] for one in kept.messages(run["conversation_id"])
                if one.get("run_id") == run["id"] and one.get("author") == "agent"
                and (one.get("text") or "").strip()
            )
        if said.strip() and became == "finished":
            return said.strip()
        return f"schedule '{named}' {became}" + (f"\n\n{said}" if said.strip() else "")

    def _make_room(self) -> None:
        """Drop the oldest conversations that have nothing running in them.

        Oldest first, and never one that is busy: what is held for a conversation is only
        what a running turn needs, and where the conversation actually got to lives in the
        agent's own record under a name that finds it again.
        """
        while len(self.exchanges) >= CONVERSATIONS:
            idle = [one for one, held in self.exchanges.items()
                    if held.task is None or held.task.done()]
            if not idle:
                return   # every one of them is working, and none is ours to drop
            self.exchanges.pop(idle[0], None)

    async def _while_running(self, held: Exchange, it: dict) -> None:
        """A second message during a running turn, which is the ordinary case.

        A brain that said it can be steered is given the words now, so they reach the turn
        that is already running rather than a new one that has forgotten what it was about.
        One that cannot is not asked to — holding words for a brain that will never read
        them again is a turn that never ends — so they wait and become the next turn.
        """
        # Retained even when offered for steering. The running task can outlive the
        # provider-input consumer during answer cleanup; putting words on that dead
        # consumer and forgetting them lost the message. It leaves this list only when
        # `_saying` confirms the provider requested it, or when `_next` admits it as the
        # next turn (R-CH-25).
        waiting = Waiting(_asked(it), it["user"], it.get("ref"), self._from(it))
        held.waiting.append(waiting)
        if len(held.waiting) > WAITING:
            # Bounded, and said. One person typing faster than an agent can answer must
            # not be able to hand themselves the whole gateway.
            held.waiting.pop(0)
            self._note(f"channel '{self.channel}': more was said than could be kept waiting")
        if not held.forgotten and held.can.get("steer") and held.saying is not None:
            # Words only. Standing instructions were given to this turn when it started
            # and a brain does not read them twice — repeating them with every steer is
            # the owner's paragraph landing again in the middle of an answer.
            self._offer(held, waiting)

    async def _control(self, it: dict) -> None:
        """A gesture aimed at the conversation, not an answer to it (R-CH-9, R-CH-10).

        **What a control did comes back as the turn's own outcome**, never as an answer to
        the gesture. Acknowledging one with the running turn's half-written output is how a
        half-finished sentence gets published as though it were the reply (R-DIS-12).
        """
        if not channel.allowed(self.record, it["user"]):
            return
        held = self.exchanges.get(it["conversation"])
        if it["control"] == channel.RESTART:
            # Aimed at the agent rather than at this conversation, so every turn on every
            # conversation ends with it. Said before it happens, because the thing that
            # would report it afterwards is the thing going away.
            self._note(f"channel '{self.channel}': a restart was asked for")
            if self._restarting is None:
                return
            self._restarting()
            return
        if it["control"] == channel.STOP:
            if held is None or held.task is None or held.task.done():
                return
            held.stopped = True
            # **What was said behind this turn is stopped with it** (R-CH-9). A turn ending
            # promotes whatever queued behind it, and a cancelled turn ends like any other —
            # so a stop drained the backlog instead of ending it and the agent carried on a
            # second later with the next message, leaving no way to actually stop short of
            # one stop per queued message, each racing the turn it had just started.
            #
            # This conversation's only: `held` is one conversation's exchange, so a stop in
            # one room ends that room's turn and backlog and leaves every other room's
            # running turn and waiting messages untouched. Anything said *after* the stop
            # queues afresh and is answered, because a person who stops and then says
            # something new is asking for the new thing.
            dropped, held.waiting = len(held.waiting), []
            held.task.cancel()
            if dropped:
                self._note(
                    f"channel '{self.channel}': a stop ended the turn and dropped "
                    f"{dropped} waiting message{'' if dropped == 1 else 's'}"
                )
            return
        # Forgetting is about where the conversation had got to, and it ends no turn: a
        # person asking to start again is not asking to throw away the answer they are
        # waiting for.
        #
        # **But a turn already running will write down where it got to when it ends**,
        # and that lands after this — so forgetting mid-turn was undone a few seconds
        # later by the turn it deliberately did not interrupt, and the next message
        # carried on from the conversation somebody had just asked to leave (R-CH-10).
        # Marked here and forgotten again once the turn has settled, which is the only
        # point after which nothing else is going to write.
        held = self.exchanges.get(it["conversation"])
        if held is not None and held.task is not None and not held.task.done():
            held.forgotten = True
        self._forget(it["conversation"])
        self._note(f"channel '{self.channel}': a conversation was forgotten")

    async def _query(self, it: dict) -> None:
        """Answer a read-only gateway question without starting a brain turn (R-CAD-17).

        Authorization stays in the same place as messages and controls. The adapter may
        prefilter to avoid visible work, but only this decision is trusted.
        """
        if not channel.allowed(self.record, it["user"]):
            return
        if self._querying is None:
            text = "This gateway does not provide that information."
        else:
            try:
                text = str(self._querying(it["query"]))
            except Exception as why:  # noqa: BLE001 — an inspection boundary
                self._note(
                    f"channel '{self.channel}': {it['query']} could not be read: {why}"
                )
                text = f"{it['query']}: unavailable"
        self._tell(
            type="query-result", conversation=it["conversation"],
            query=it["query"], ref=it["ref"], text=text,
        )

    async def _configure(self, it: dict) -> None:
        """Change an agent default only after the channel authorization boundary."""
        if not channel.may_configure(self.record, it["user"]):
            return
        named = it["provider"]
        try:
            provider.program(named)
            conversation = store.conversation_id(
                self.channel, it["conversation"])
            agents.remember(
                self.name, self._where, provider=named, replace_brain=True,
                forget_conversation=conversation)
            held = self.exchanges.get(it["conversation"])
            if held is not None and held.task is not None and not held.task.done():
                # The active turn keeps what it settled; when it ends, forget again so
                # its old provider session cannot undo the fresh start (R-CH-26).
                held.forgotten = True
            text = f"Default provider changed to {named}. The next message starts fresh."
            self._note(
                f"channel '{self.channel}': default provider changed to {named}")
        except (provider.NotRunnable, store.Unreadable, store.TooNew,
                store.Behind, migration.Failed) as why:
            text = f"Provider was not changed: {why}"
        except Exception as why:  # noqa: BLE001 — a persisted configuration boundary
            text = f"Provider was not changed: {why}"
        self._tell(
            type="configure-result", conversation=it["conversation"],
            ref=it["ref"], text=text,
        )

    def _forget(self, conversation: str) -> None:
        """Throw away where this conversation had got to, under every brain it has had.

        Under every brain, because an agent whose provider changed has conversations
        under both — and leaving one behind means the next message carries on from a
        session somebody just asked to be rid of. Asked of the conversation rather than
        walked brain by brain: which brains it has had is the record's to know.
        """
        agents.records(self.name, self._where).forget_session(
            store.conversation_id(self.channel, conversation))

    async def _recover(self) -> None:
        """Claim and continue each turn a predecessor stopped on this channel (R-GW-22)."""
        if self._recovered or self._stopping:
            return
        self._recovered = True
        kept = agents.records(self.name, self._where)
        for interrupted in kept.recoverable(self.channel):
            if not kept.claim_recovery(interrupted["id"], store.stamped()):
                continue
            conversation = interrupted["conversation"]
            held = self.exchanges.get(conversation)
            if held is None:
                self._make_room()
                held = self.exchanges.setdefault(conversation, Exchange(conversation))
            if held.task is not None and not held.task.done():
                self._note(
                    f"channel '{self.channel}': interrupted run {interrupted['id']} "
                    "could not be resumed because its conversation is already running"
                )
                self._say(
                    channel.FAILED, held,
                    why="the interrupted turn could not be resumed because its conversation "
                        "is already running",
                )
                continue
            held.run = interrupted["id"]
            held.stopped = False
            held.task = asyncio.ensure_future(
                self._one(
                    held, CONTINUE, interrupted.get("user") or "",
                    recovery_of=interrupted,
                )
            )

    # -- one turn --------------------------------------------------------------------

    async def _one(self, held: Exchange, prompt: str, user: str, preface: str = "",
                   recovery_of: dict | None = None, prompt_author: str = "user",
                   on_admitted=None) -> None:
        """Carry one turn, and say how it stands at each point rundesk decides it."""
        chose = recovery_of or agents.chosen(self.name, self._where)
        held.saying = asyncio.Queue()
        # Emptied for each turn. Left standing, what the *last* turn ended on was still
        # in hand when this one began — so the first finished thing said here pushed the
        # previous turn's answer out as a remark, and every turn after the first posted
        # one message too many, quoting itself from a minute ago.
        held.spoken = []
        held.run = recovery_of["id"] if recovery_of else None
        shown = _Shown(self, held)
        self._say(channel.TAKEN, held, ref=held.ref)
        outcome = None
        kept = agents.records(self.name, self._where)

        def admitted(run, can):
            self._took(held, run, can)
            if recovery_of:
                kept.recovery_began(recovery_of["id"], run, store.stamped())
            if on_admitted is not None:
                on_admitted(run)

        try:
            outcome = await self._carry(
                self.name, prompt, chose.get("provider") or "",
                where=self._where,
                model=chose.get("model"),
                settings=chose.get("settings"),
                conversation=held.conversation,
                on=self.channel,
                kind=str(self.record.get("kind") or ""),
                watching=shown,
                steering=_saying(held.saying),
                asked_by={"channel": self.channel, "on": held.conversation, "user": user},
                admitted=admitted,
                preface=preface,
                resume_required=bool(recovery_of),
                prompt_author="rundesk" if recovery_of else prompt_author,
                recovery_of=recovery_of["id"] if recovery_of else None,
                resume_on_interrupt=lambda: (
                    self._stopping and not held.stopped and recovery_of is None
                ),
                stopped_by_owner=lambda: held.stopped,
                **({"posture": recovery_of["posture"]} if recovery_of else {}),
            )
        except asyncio.CancelledError:
            # Asked for, or the gateway going. Either way the turn is over and the
            # surface is told which of the two it was.
            self._say(channel.STOPPED if held.stopped else channel.FAILED, held,
                      ref=held.ref, why=None if held.stopped else "the gateway stopped")
            raise
        except BaseException as went_wrong:  # noqa: BLE001 — a process boundary
            # Nobody awaits this task, so anything raised here is raised nowhere at all.
            # A turn that failed and said nothing is one somebody is still waiting on.
            self._note(f"channel '{self.channel}': a turn could not be carried: {went_wrong}")
            self._say(channel.FAILED, held, ref=held.ref, why=str(went_wrong))
        else:
            await self._answer(held, outcome, provider.label(chose.get("provider") or ""))
            self._say(channel.FINISHED if outcome.ok else channel.FAILED, held,
                      ref=held.ref, why=None if outcome.ok else _why(outcome))
        finally:
            held.saying.put_nowait(None)
            held.saying = None
            held.can = {}
            if self._restart_waiting(held.run):
                # The provider has ended, but its answer and finished mark may still be
                # waiting for the adapter. Release the external restart worker only
                # after that outbound queue has drained (R-GW-43).
                await self._showing.join()
                self._restart_ready(held.run)
            if held.forgotten:
                # After the turn, never before: this is the first moment at which
                # nothing else is going to write where the conversation got to.
                held.forgotten = False
                self._forget(held.conversation)
            asyncio.ensure_future(self._next(held))

    async def _next(self, held: Exchange) -> None:
        """Whatever was said while the last turn ran, now that there is nothing running.

        Never once this channel is going away. What is waiting is lost, and that is the
        right loss: it was never started, nothing has been said about it, and the
        alternative is a brain running for a channel that has already been reported gone.
        """
        if self._stopping or not held.waiting:
            return
        waiting = held.waiting.pop(0)
        held.ref = waiting.ref
        held.stopped = False
        held.task = asyncio.ensure_future(
            self._one(held, waiting.text, waiting.user, waiting.preface)
        )

    def _took(self, held: Exchange, run: str, can: dict) -> None:
        """The run this conversation became and what its brain can do, the moment both
        are known (R-CH-15, R-CAD-4).

        Together, because they arrive together and a surface needs both before it shows
        anything: the run to correlate the marks it is about to make, and the
        capabilities to avoid offering what cannot happen.
        """
        held.run = run
        held.can = dict(can)
        # Anything said while this turn was being admitted goes into it rather than
        # queueing behind it (R-CH-9).
        if held.can.get("steer") and held.saying is not None:
            for waiting in list(held.waiting):
                self._offer(held, waiting)
        self._say(channel.RUNNING, held)

    @staticmethod
    def _offer(held: Exchange, waiting: Waiting) -> None:
        """Offer retained words and remove them only after the consumer sent them."""
        def pending() -> bool:
            return any(candidate is waiting for candidate in held.waiting)

        def accepted() -> None:
            for index, candidate in enumerate(held.waiting):
                if candidate is waiting:
                    held.waiting.pop(index)
                    return

        held.saying.put_nowait((waiting.text, waiting.user, pending, accepted))

    async def _answer(self, held: Exchange, outcome, provider_name: str) -> None:
        """What the agent said, handed over once and whole (R-CH-8, R-CH-28).

        Held until here rather than shown as it was written. A reply that rewrites itself
        in place is unreadable, and the adapter is never given the chance to try: nothing
        of the brain's prose crosses the seam before this. The resolved provider belongs
        on this final record rather than on optional usage: every answer has one, even
        when its brain reports no model or token counts.
        """
        # Whatever is still in hand: the last complete thing said, or every fragment of
        # a reply that was written a piece at a time. Either way it is the answer.
        text = "".join(one for _was, one in held.spoken).strip() or outcome.text.strip()
        text, linked = _attachment_lines(text)
        made = await self._made([*linked, *outcome.files])
        if not text and not made:
            return
        self._tell(type="answer", conversation=held.conversation, run=held.run,
                   provider=provider_name, text=text, attachments=made)

    async def _made(self, declared) -> list:
        """What the brain declared for delivery, as things a surface may actually send.

        Provider file records and whole-line local file links in the final answer are
        explicit declarations. **Only from where this agent works.** A path is checked
        against the agent's own directories before anything leaves the machine — the
        brain runs as the owner and can read anything they can, so "the brain asked for
        it" is not on its own a reason to put a file into a chat room (R-CH-13, R-CH-31).
        """
        whose = agents.paths(self.name, self._where)
        mine = [whose["workspace"], whose["logs"], whose["home"]]
        found = []
        seen = set()
        seen_files = set()
        candidates = []
        declared_paths = set()
        for candidate in declared:
            at = candidate.get("at") if isinstance(candidate, dict) else None
            identity = os.path.normpath(at) if isinstance(at, str) else None
            if identity is not None and identity in declared_paths:
                continue
            if identity is not None:
                declared_paths.add(identity)
            candidates.append(candidate)
            if len(candidates) > channel.ATTACHED_MOST:
                break
        for one in candidates[:channel.ATTACHED_MOST]:
            attachment, why = await asyncio.to_thread(_approved_attachment, one, mine)
            if why:
                self._note(f"channel '{self.channel}': {why}")
            if attachment is None:
                continue
            file_identity = attachment.pop("_file_identity")
            if attachment["at"] in seen or file_identity in seen_files:
                continue
            seen.add(attachment["at"])
            seen_files.add(file_identity)
            found.append(attachment)
        if len(candidates) > channel.ATTACHED_MOST:
            self._note(f"channel '{self.channel}': sending only the first "
                       f"{channel.ATTACHED_MOST} attachments")
        return found

    def _say(self, state: str, held: Exchange, ref=None, why=None) -> None:
        """How the turn stands, which is rundesk's to decide (R-CAD-3)."""
        said = {"type": "state", "conversation": held.conversation, "run": held.run,
                "state": state}
        if ref:
            said["ref"] = ref
        if why:
            said["why"] = why
        if held.can:
            # What the *brain* can do, so a surface never offers to interrupt one that
            # said it cannot be (R-CAD-4).
            said["can"] = dict(held.can)
        self._tell(**said)

    def _tell(self, **it) -> None:
        """Put one record in the queue for the adapter, in the order it was decided.

        Never awaited by whatever decided it: a turn must not be held up by how fast a
        chat platform accepts writes, and the record it is showing is already true.
        """
        self._showing.put_nowait(it)
        if self._writer is None or self._writer.done():
            self._writer = asyncio.ensure_future(self._show())

    async def _show(self) -> None:
        """Hand records to the adapter, one at a time, and never at the turn's expense
        (R-CH-12).

        A delivery that fails is a delivery that failed. It is written to the gateway's
        log and the turn goes on: the brain is doing work somebody asked for, and losing
        it because a chat platform was busy would be losing the thing of value to protect
        the thing showing it.
        """
        while True:
            try:
                it = self._showing.get_nowait()
            except asyncio.QueueEmpty:
                return
            try:
                await self._sending(channel.spoken(**it))
            except asyncio.CancelledError:
                raise
            except BaseException as why:  # noqa: BLE001 — a delivery boundary
                self._note(f"channel '{self.channel}': could not show "
                           f"{it.get('type')}: {why}")
            finally:
                self._showing.task_done()

    # -- going away ------------------------------------------------------------------

    async def stop(self) -> None:
        """End every turn this channel is carrying, and wait for each to unwind.

        Said *before* anything is cancelled. A turn ending schedules whatever was waiting
        behind it, from a `finally` that runs during the cancelling — so a snapshot taken
        first and awaited afterwards missed exactly the turn that shutdown created, and
        left a brain running for a channel already reported gone (R-CH-11).

        Looked at again after awaiting, rather than once: the point is that this list can
        grow while it is being drained.
        """
        self._stopping = True
        for _ in range(_UNWINDING):
            running = [held.task for held in self.exchanges.values()
                       if held.task is not None and not held.task.done()]
            if not running:
                break
            for task in running:
                task.cancel()
            for task in running:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        # What was decided before the end is still worth showing, and it is a bounded
        # amount: the last mark on every conversation that was running.
        if self._writer is not None and not self._writer.done():
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._writer
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await self._show()


class _Shown:
    """What the agent did and said, shown while it is still doing it (R-CH-6).

    **A part-written reply is not passed on here.** `text` arrives a fragment at a time;
    it is collected by the turn and handed over whole at the end. What is passed on is
    what is whole the moment it exists (R-CH-7) — a tool it ran, a thought it closed,
    what it cost, and a complete thing said with more of the turn still to come.

    **An owner who turned activity off turned all of it off**, prose included, and such a
    channel posts one message for the turn: its answer (R-CH-6, R-CH-27). A quiet room that
    answers late does look broken, which is why this is on unless somebody said so — but
    somebody who said so chose silence over reassurance, and prose is the most text a turn
    makes.

    Only ever the brain's own records: what rundesk makes of a turn does not come through
    here, and a watcher waiting for one of rundesk's own kinds would wait for ever.
    """

    #: A complete thing said mid-turn, which is shown, as against a fragment of a reply
    #: still being written, which is not (R-CH-19).
    WHOLE = "whole"

    #: What a surface is shown as it happens, and exactly which of each record's fields
    #: leave this machine (R-CH-13).
    #:
    #: **Named rather than filtered**, so the default for anything new is that it stays.
    #: A brain is free to add fields nobody here knows and they are kept in the account —
    #: which is the whole reason a record of an unknown shape is not refused — but a
    #: tool's own arguments, a file it read, a command's whole output and whatever a
    #: vendor decides to attach next year are exactly the things that must not be posted
    #: into a chat room because somebody added a key. `text` is absent for a different
    #: reason: what is said is decided a record at a time by `_spoke`, because whether a
    #: thing said is a remark or the answer is knowable only from what follows it (R-CH-19).
    AS_IT_HAPPENS = {
        "think": ("text",),
        "tool": ("id", "name", "did"),
        "result": ("id", "ok", "summary"),
        "usage": ("input", "output", "cached", "written", "session", "model"),
    }

    #: How much of a summary a surface is shown. A brain is entitled to hand back the
    #: whole of what a command printed, and that is worth keeping in the account and
    #: worth not pasting into a room somebody else can read.
    SUMMARY_CHARS = 200

    def __init__(self, answering: "Answering", held: Exchange):
        self._answering, self._held = answering, held

    def __call__(self, said: dict) -> None:
        kind = said.get("type")
        if kind == "text":
            # Always, whether or not this channel is shown the turn: what was said is the
            # material the answer is made of, and only whether the earlier ones are posted
            # depends on the owner's choice.
            self._spoke(said)
            return
        if kind not in self.AS_IT_HAPPENS:
            return
        if not self._shown():
            return
        it = {what: said[what] for what in self.AS_IT_HAPPENS[kind] if what in said}
        if kind == "tool" and it.get("did") == "delegate" and "who" in said:
            # The one narrow exception: a provider-supplied helper name may accompany the
            # closed `delegate` verb. A `who` attached to any other tool remains private.
            it["who"] = said["who"]
        if isinstance(it.get("summary"), str) and len(it["summary"]) > self.SUMMARY_CHARS:
            it["summary"] = it["summary"][: self.SUMMARY_CHARS] + "…"
        self._answering._tell(
            type=kind, conversation=self._held.conversation, run=self._held.run, **it)

    def _shown(self) -> bool:
        """Whether this channel is shown the turn while it runs (R-CH-6)."""
        return bool(self._answering.record.get("activity", True))

    def _spoke(self, said: dict) -> None:
        """A thing the brain said, shown now if it is finished and there is more coming.

        A fragment of a reply still being written is kept for the end, because showing it
        means showing a sentence that changes under somebody reading it. A *complete*
        thing said while the turn runs is shown as soon as the next one arrives — which
        is what makes the last one the answer, and is only knowable once there is a next.

        **Unless the owner turned activity off**, in which case none of them is posted and
        the turn's one message is its answer (R-CH-27). What is said mid-turn is the most
        text a turn produces, so leaving it out of that choice overrode it on the record
        that mattered most. Kept either way: what was said is still written into the
        account and into the run's records, and this decides only what is posted.
        """
        text = str(said.get("text") or "")
        if not said.get(self.WHOLE):
            self._held.spoken.append(("fragment", text))
            return
        posts = self._shown()
        for was, older in list(self._held.spoken):
            if posts and was == "whole" and older.strip():
                self._answering._tell(type="said", conversation=self._held.conversation,
                                      run=self._held.run, text=older.strip())
            self._held.spoken.remove((was, older))
        self._held.spoken.append(("whole", text))


def _handoff_text(handoff: dict) -> str:
    """One role handoff, as the named parent is given it to read.

    What Rundesk knows and what the worker said, told apart on the page. Nothing here is
    read out of the report or summarised from it: a line saying the tests passed would be
    Rundesk asserting the one thing the review exists to establish (R-ROL-16).
    """
    said = [
        f"Role: {handoff.get('role') or ''}",
        f"Role run: {handoff.get('role_run') or ''}",
        f"Outcome the worker's turn reached: {handoff.get('outcome') or ''}",
    ]
    if handoff.get("target"):
        said.append(f"Worked in: {handoff['target']}")
    if handoff.get("files"):
        said.append("Files it said it made: " + ", ".join(str(one)
                                                          for one in handoff["files"]))
    said.append("")
    said.append("Its report, in its own words, unchecked:")
    said.append("")
    said.append(str(handoff.get("report") or "(it said nothing)"))
    return "\n".join(said)


async def _saying(queue: asyncio.Queue):
    """Everything said to a turn while it runs, a word at a time.

    Ends when the queue is closed with `None`, which is what the turn ending does — a
    generator that never ended would hold a brain's input open after its work was over.
    """
    while True:
        offered = await queue.get()
        if offered is None:
            return
        word, who, pending, accepted = offered
        if not pending():
            continue
        # Said with who said it, so a word steered into a running turn is written down
        # under the same identity as the message that started it (R-STO-27).
        yield turn.Said(word, who)
        # Reached only when the consumer asks for another word, which happens after it
        # finished sending this one. If its send failed because the provider had already
        # closed input, the async-for loop exits and this retained message becomes the
        # next turn instead (R-CH-25).
        accepted()


def _approved_attachment(declared, roots) -> tuple[dict | None, str | None]:
    """Resolve, contain, and fingerprint one declaration without trusting its path."""
    if not isinstance(declared, dict):
        return None, None
    at = declared.get("at")
    if not isinstance(at, str) or not at or not Path(at).is_absolute():
        return None, None
    try:
        where = Path(at).resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return None, None
    inside = None
    for candidate in roots:
        try:
            root = candidate.resolve(strict=True)
            where.relative_to(root)
        except (OSError, RuntimeError, ValueError):
            continue
        inside = root
        break
    if inside is None:
        return None, f"not sending {where}, which is outside where this agent works"
    try:
        fingerprint = _fingerprint_beneath(where, inside)
    except OSError as why:
        return None, f"not sending {where.name}: {why}"
    if fingerprint is None:
        return None, f"not sending {where.name}, which is too large to attach"
    size, digest, file_identity = fingerprint
    return {
        "name": str(declared.get("name") or where.name),
        "at": str(where),
        "bytes": size,
        "sha256": digest,
        "_file_identity": file_identity,
    }, None


def _fingerprint_beneath(at: Path, inside: Path) -> tuple[int, str, tuple[int, int]] | None:
    """Read through held directory descriptors, refusing links in every component."""
    at.relative_to(inside)
    parts = at.parts[1:]
    if not parts:
        raise OSError("not a regular file")
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    descriptor = None
    digest = hashlib.sha256()
    size = 0
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(
            parts[-1], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
            dir_fd=directory,
        )
        status = os.fstat(descriptor)
        if not stat.S_ISREG(status.st_mode):
            raise OSError("not a regular file")
        with os.fdopen(descriptor, "rb") as source:
            descriptor = None
            while block := source.read(min(1024 * 1024,
                                            channel.ATTACHED_BYTES + 1 - size)):
                size += len(block)
                if size > channel.ATTACHED_BYTES:
                    return None
                digest.update(block)
        return size, digest.hexdigest(), (status.st_dev, status.st_ino)
    finally:
        os.close(directory)
        if descriptor is not None:
            os.close(descriptor)


def _attachment_lines(text: str) -> tuple[str, list]:
    """Extract absolute local Markdown links and leave only their labels."""
    declared = []
    visible = []
    copied = 0
    searched = 0
    while found := _LOCAL_ATTACHMENT_START.search(text, searched):
        start = found.start()
        # `\rundesk-attach:` is the documented literal form. Without this check the
        # optional prefix would let the search begin again at its otherwise ordinary `[`.
        line_start = text.rfind("\n", 0, start) + 1
        before = text[line_start:start]
        if found.group(0) == "[" and re.search(
                r"\\rundesk-attach:[ \t]+$", before):
            searched = found.end()
            continue

        label_start = found.end()
        label_end = _matching_close(text, label_start, "[", "]")
        if label_end is None or label_end + 1 >= len(text) or text[label_end + 1] != "(":
            searched = found.end()
            continue

        destination_start = label_end + 2
        if destination_start >= len(text):
            break
        if text[destination_start] == "<":
            destination_end = _next_unescaped(text, destination_start + 1, ">")
            if (destination_end is None or destination_end + 1 >= len(text)
                    or text[destination_end + 1] != ")"):
                searched = found.end()
                continue
            at = text[destination_start + 1:destination_end]
            end = destination_end + 2
        else:
            destination_end = _matching_close(text, destination_start, "(", ")")
            if destination_end is None:
                searched = found.end()
                continue
            at = text[destination_start:destination_end]
            end = destination_end + 1

        if not at.startswith("/") or at.startswith("//") or "\n" in at or "\r" in at:
            searched = found.end()
            continue
        if found.group(0).startswith("rundesk-attach:"):
            # Preserve the reserved whole-line form's historical CRLF normalization and
            # trailing-space handling without consuming prose after an ordinary link.
            line_end = end
            while line_end < len(text) and text[line_end] in " \t":
                line_end += 1
            if line_end < len(text) and text[line_end] == "\r":
                line_end += 1
            if line_end == len(text) or text[line_end] == "\n":
                end = line_end
        visible.extend((text[copied:start], text[label_start:label_end]))
        declared.append({"name": Path(at).name, "at": at})
        copied = end
        searched = end
    visible.append(text[copied:])
    return "".join(visible), declared


def _matching_close(text: str, start: int, opened: str, closed: str) -> int | None:
    """Find a balanced Markdown delimiter, ignoring escaped characters."""
    depth = 1
    index = start
    while index < len(text):
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == opened:
            depth += 1
        elif text[index] == closed:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _next_unescaped(text: str, start: int, wanted: str) -> int | None:
    """Find one Markdown delimiter, ignoring escaped characters."""
    index = start
    while index < len(text):
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == wanted:
            return index
        index += 1
    return None


def _asked(it: dict) -> str:
    """What the person asked, including attachments and explicit reply context.

    A brain is given a prompt, so what somebody attached reaches it the only way
    anything reaches it: named in the words of the turn, by a path on this machine that
    the agent can open. Rundesk does not read the file and does not describe it — what it
    is is the brain's to find out, with the tools it already has.

    Where it was said does **not** come through here (R-CH-21, R-CH-22). Folded in, it
    arrived as part of what the person typed, so a brain could not tell rundesk's words
    from theirs — and answered by reporting its own situation back to them as though they
    had asked about it. It goes over as its own thing instead.
    """
    said = it.get("text") or ""
    brought = it.get(channel.ATTACHED) or []
    if brought:
        named = "\n".join(f"- {one['name']}: {one['at']}" for one in brought)
        said = f"{said}\n\nAttached to this message, on this machine:\n{named}"
    reply = it.get(channel.REPLY_TO)
    if reply:
        identifier = reply["id"]
        if reply["resolved"]:
            author = f" from {reply['author']}" if reply.get("author") else ""
            quoted = reply.get("text") or "(no text content)"
            context = (
                f"This message replies to conversation message {identifier}{author}.\n"
                f"Quoted message: {quoted}"
            )
        else:
            context = (
                f"This message replies to conversation message {identifier} "
                "(quoted text unavailable)."
            )
        said = f"{said}\n\n--\n\n{context}"
    return said.strip()



def _why(outcome) -> str:
    """What to tell a surface about a turn that did not work, in one line."""
    return getattr(outcome, "why", None) or outcome.reason
