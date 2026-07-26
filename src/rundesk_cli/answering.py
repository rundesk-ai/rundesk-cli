"""What arrives on a channel, carried through to an answer.

The only module that knows `channel`, `turn`, `session` and `agent` all exist — the mirror
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

from rundesk_cli import agent as agents
from rundesk_cli import channel, session, turn

#: How many messages may be waiting for a conversation whose brain cannot be steered.
#: Small on purpose: somebody typing while an agent works is answering the conversation,
#: not queueing a batch of work, and an unbounded queue is a way to hand one person the
#: whole gateway. Past it the oldest waiting message goes and is said to have.
WAITING = 4

#: What a conversation is called in the run's account, so two channels cannot collide on
#: one name and a session kept for a Discord thread is never handed to a Slack one.
def named(channel_name: str, conversation: str) -> str:
    """One conversation, named so it is this channel's and no other's (R-CH-3)."""
    return f"{channel_name}/{conversation}"


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
        self.saying: asyncio.Queue | None = None
        self.waiting: list = []
        self.stopped = False


class Answering:
    """One channel's worth of conversations, and the turns running in them.

    Everything it needs to reach the world is passed in: `sending` is how a record reaches
    the adapter, and `carry` is what runs a turn. Both are arguments so the whole of this
    is exercised with no adapter, no brain and no network anywhere near it.
    """

    def __init__(self, name: str, channel_name: str, record: dict, sending,
                 where=None, carry=None, note=None, restarting=None):
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
        self.exchanges: dict = {}
        self.connected = False
        #: Everything on its way to the adapter, in the order it was decided. One queue
        #: and one writer, because a mark saying a turn is finished must not overtake the
        #: answer it is finishing — and a record shown out of order is worse than one not
        #: shown at all, since a reader has no way to tell.
        self._showing: asyncio.Queue = asyncio.Queue()
        self._writer: asyncio.Task | None = None

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
        elif kind == "gone":
            # Said, never acted on. Coming back is the adapter's own (R-CAD-7), and a
            # turn already running is not interrupted by the surface it will be shown on.
            self.connected = False
            self._note(f"channel '{self.channel}' lost its connection: {it.get('why') or 'no reason given'}")
        elif kind == "arrived":
            await self._arrived(it)
        elif kind == "control":
            await self._control(it)

    async def _arrived(self, it: dict) -> None:
        if not channel.allowed(self.record, it["user"]):
            # Silence, and never a refusal. Answering a stranger to tell them they are a
            # stranger confirms the agent is listening and spends the owner's tokens
            # doing it (R-CH-4).
            self._note(f"channel '{self.channel}': a message from someone not allowed was not dispatched")
            return
        held = self.exchanges.setdefault(it["conversation"], Exchange(it["conversation"]))
        if held.task is not None and not held.task.done():
            await self._while_running(held, it)
            return
        held.ref = it.get("ref")
        held.stopped = False
        held.task = asyncio.ensure_future(self._one(held, it["text"], it["user"]))

    async def _while_running(self, held: Exchange, it: dict) -> None:
        """A second message during a running turn, which is the ordinary case.

        A brain that said it can be steered is given the words now, so they reach the turn
        that is already running rather than a new one that has forgotten what it was about.
        One that cannot is not asked to — holding words for a brain that will never read
        them again is a turn that never ends — so they wait and become the next turn.
        """
        if held.can.get("steer") and held.saying is not None:
            held.saying.put_nowait(it["text"])
            return
        # Whether the brain can be steered is not known until the turn is admitted, and a
        # burst arrives faster than that. So it waits here and is drained into the running
        # turn the moment the answer comes back — otherwise the first message of every
        # burst is steered and the rest become turns of their own, which is the same
        # conversation answered twice over.
        held.waiting.append((it["text"], it["user"], it.get("ref")))
        if len(held.waiting) > WAITING:
            # Bounded, and said. One person typing faster than an agent can answer must
            # not be able to hand themselves the whole gateway.
            held.waiting.pop(0)
            self._note(f"channel '{self.channel}': more was said than could be kept waiting")

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
            held.task.cancel()
            return
        # Forgetting is about where the conversation had got to, and touches no turn.
        # A turn still running is left to finish and, having been forgotten, its handle
        # is not written back — the next message starts fresh either way.
        whose = agents.paths(self.name, self._where)["agent"]
        for brain in session.brains(whose):
            session.forget(whose, brain, named(self.channel, it["conversation"]))
        self._note(f"channel '{self.channel}': a conversation was forgotten")

    # -- one turn --------------------------------------------------------------------

    async def _one(self, held: Exchange, prompt: str, user: str) -> None:
        """Carry one turn, and say how it stands at each point rundesk decides it."""
        chose = agents.chosen(self.name, self._where)
        held.saying = asyncio.Queue()
        held.run = None
        shown = _Shown(self, held)
        self._say(channel.TAKEN, held, ref=held.ref)
        outcome = None
        try:
            outcome = await self._carry(
                self.name, prompt, chose.get("provider") or "",
                where=self._where,
                model=chose.get("model"),
                settings=chose.get("settings"),
                conversation=named(self.channel, held.conversation),
                watching=shown,
                steering=_saying(held.saying),
                asked_by={"channel": self.channel, "on": held.conversation, "user": user},
                admitted=lambda run, can: self._took(held, run, can),
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
            self._answer(held, outcome)
            self._say(channel.FINISHED if outcome.ok else channel.FAILED, held,
                      ref=held.ref, why=None if outcome.ok else _why(outcome))
        finally:
            held.saying = None
            held.can = {}
            asyncio.ensure_future(self._next(held))

    async def _next(self, held: Exchange) -> None:
        """Whatever was said while the last turn ran, now that there is nothing running."""
        if not held.waiting:
            return
        text, user, ref = held.waiting.pop(0)
        held.ref = ref
        held.stopped = False
        held.task = asyncio.ensure_future(self._one(held, text, user))

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
            while held.waiting:
                text, _user, _ref = held.waiting.pop(0)
                held.saying.put_nowait(text)
        self._say(channel.RUNNING, held)

    def _answer(self, held: Exchange, outcome) -> None:
        """What the agent said, handed over once and whole (R-CH-8).

        Held until here rather than shown as it was written. A reply that rewrites itself
        in place is unreadable, and the adapter is never given the chance to try: nothing
        of the brain's prose crosses the seam before this.
        """
        text = outcome.text.strip()
        if not text:
            return
        self._tell(type="answer", conversation=held.conversation, run=held.run,
                   text=text)

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

    # -- going away ------------------------------------------------------------------

    async def stop(self) -> None:
        """End every turn this channel is carrying, and wait for each to unwind."""
        running = [held.task for held in self.exchanges.values()
                   if held.task is not None and not held.task.done()]
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
    """What the agent did, shown while it is still doing it (R-CH-6).

    **Prose is not passed on here.** `text` is what the brain *says*, and it arrives a
    fragment at a time; it is collected by the turn and handed over whole at the end. What
    is passed on is what the agent *did* — a tool it ran, a thought it closed, what it
    cost — each of which is whole the moment it exists (R-CH-7).

    Only ever the brain's own records: what rundesk makes of a turn does not come through
    here, and a watcher waiting for one of rundesk's own kinds would wait for ever.
    """

    #: What a surface is shown as it happens, and exactly which of each record's fields
    #: leave this machine (R-CH-13).
    #:
    #: **Named rather than filtered**, so the default for anything new is that it stays.
    #: A brain is free to add fields nobody here knows and they are kept in the account —
    #: which is the whole reason a record of an unknown shape is not refused — but a
    #: tool's own arguments, a file it read, a command's whole output and whatever a
    #: vendor decides to attach next year are exactly the things that must not be posted
    #: into a chat room because somebody added a key. `text` is absent for a different
    #: reason: prose is handed over whole at the end (R-CH-7).
    AS_IT_HAPPENS = {
        "think": ("text",),
        "tool": ("id", "name", "did"),
        "result": ("id", "ok", "summary"),
        "usage": ("input", "output", "cached", "model"),
    }

    #: How much of a summary a surface is shown. A brain is entitled to hand back the
    #: whole of what a command printed, and that is worth keeping in the account and
    #: worth not pasting into a room somebody else can read.
    SUMMARY_CHARS = 200

    def __init__(self, answering: "Answering", held: Exchange):
        self._answering, self._held = answering, held

    def __call__(self, said: dict) -> None:
        kind = said.get("type")
        if kind not in self.AS_IT_HAPPENS:
            return
        it = {what: said[what] for what in self.AS_IT_HAPPENS[kind] if what in said}
        if isinstance(it.get("summary"), str) and len(it["summary"]) > self.SUMMARY_CHARS:
            it["summary"] = it["summary"][: self.SUMMARY_CHARS] + "…"
        self._answering._tell(
            type=kind, conversation=self._held.conversation, run=self._held.run, **it)


async def _saying(queue: asyncio.Queue):
    """Everything said to a turn while it runs, a word at a time.

    Ends when the queue is closed with `None`, which is what the turn ending does — a
    generator that never ended would hold a brain's input open after its work was over.
    """
    while True:
        word = await queue.get()
        if word is None:
            return
        yield word


def _why(outcome) -> str:
    """What to tell a surface about a turn that did not work, in one line."""
    return getattr(outcome, "why", None) or outcome.reason
