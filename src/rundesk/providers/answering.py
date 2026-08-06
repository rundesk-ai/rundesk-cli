"""What answers a message, and what starts a scheduled turn. The two seams, filled.

`channels.hosting` and `schedules.firing` each publish a shape and take an object of it, because
neither may reach this package — what a channel *is* and when a schedule is *due* have to stay
answerable by a case with no brain, no adapter and no subprocess anywhere near them. This is the
object, and `gateways.host` is the one layer that may reach both to hand it over.

## A message and a schedule are answered differently, and it is not a preference

**A channel turn runs on a thread of its own and returns at once.** `hosting` calls this on the
thread reading one adapter's output, and that thread's whole contract is that it cannot fall behind:
a turn takes minutes, and running one inline would stop the channel reading anything for the length
of it — including the next message, including a `stop`.

**A scheduled turn is a process of its own.** `firing` hands out a lock descriptor and expects a pid
back, because that is how a schedule's claim survives the gateway that started it. So this spawns
`rundesk providers run`, which takes the turn in that process — the same `turns.run`, in a different
place.

Both end in the same function. There is one turn implementation and there are three callers of it.

## What a channel sees while a turn runs

The four words `hosting` already renders and never names: `working` when a turn is admitted, and one
of `done`, `stopped` or `failed` when it settles. **This package owns those words** and `hosting`
forwards whatever it is handed, so there is one source of truth and no constant to drift.

The answer goes back through what already exists: cut to the platform's own limit by
`channels.delivery`, its files vetted by `channels.files`, and out through `hosting.told`.
"""

import contextlib
import datetime
import json
import threading
import time
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict, Optional

from rundesk import __version__
from rundesk.agents import directory, records
from rundesk.channels import arriving, delivery, hosting
from rundesk.channels import kept as channels_kept
from rundesk.core import config
from rundesk.providers import adapters, instructions, kept, protocol, turns
from rundesk.schedules import due, firing
from rundesk.schedules import kept as schedules_kept
from rundesk.skills import grants
from rundesk.utils import logs, programs

#: What rundesk says a turn is doing, in the words the channel layer already renders. `seen` is not
#: among them and never will be: that one belongs to a message arriving and needs no turn at all.
WORKING = "working"
DONE = "done"
STOPPED = "stopped"
FAILED = "failed"

#: Which of those a settled turn is. Read off the turn's own status rather than decided again, so a
#: surface and the records can never disagree about what happened to one run.
AS_A_STATE = {kept.DONE: DONE, kept.STOPPED: STOPPED, kept.FAILED: FAILED}

#: What a surface may spend putting the cost line above the answer, beyond the line itself. A
#: platform needs a separator and may need a register of its own around it — Discord's small print
#: is a `-# ` prefix and a newline — and none of that is rundesk's to write. Generous rather than
#: exact, because the cost of being a few characters over is a delivery the adapter refuses whole.
AROUND_THE_COST = 8

#: The one word in `protocol.DID` whose *ending* is worth showing as well as its beginning, and the
#: only one that carries a name. A subagent runs for minutes, so a reader who saw it start has been
#: waiting on something with no other sign of life; everything else in that list begins and ends
#: inside a second and its line already says what happened.
DELEGATE = "delegate"

#: How many tools in flight one turn may be remembered for. A result names the tool it belongs to,
#: so what each call *was* has to be held until that arrives — and a result that never comes is a
#: entry nothing would ever remove, on a turn that may run for an hour.
TOOLS_KEPT = 200

#: How much of a helper's name travels. **A name is a stranger's text and may be a path**: the
#: build this replaces showed a subagent's full provider location in a room. Clipped, flattened, and
#: reduced to a last component before it goes anywhere.
A_HELPER_AT_MOST = 48


#: How many times a message that found the conversation busy is offered again.
#:
#: **Not a retry of something that failed** — nothing failed. It is what a message does when the
#: turn it tried to join ended in the moment between being refused the claim and being offered as a
#: word: the way in has closed and the way round has opened, and asking once more takes it. Three,
#: because each attempt needs the one before it to have genuinely settled, and a conversation that
#: is busy three times over is one somebody is typing into faster than their agent can answer.
TRIES = 3

#: How long to wait before offering a refused message again. Long enough for a turn that was
#: settling to have settled and let go of the claim, short enough that somebody watching a room does
#: not see their message sit there.
BEFORE_ASKING_AGAIN = 0.25


class Refused(Exception):
    """A schedule that asks nobody anything, asked to take a turn.

    Named rather than answered as a sentence, because the caller is a command that has to exit
    non-zero and say what to type instead.
    """


#: What a schedule's turn is started with. `rundesk` itself, because a schedule's program may be
#: rundesk and `firing` already carries `RUNDESK_HOME` for exactly that.
THE_RUNNER = ("providers", "run")


class OnAChannel:
    """Answers a message that arrived on a channel, on a thread of its own.

    Handed to `hosting.looked`. Holds nothing but what it needs to find the gateway's own log and to
    reach the adapter again with the answer — the turn itself keeps no state here, because a turn
    that outlived the object that started it would be a turn nobody could settle.
    """

    def __init__(self, where: Path, hosted: Callable[[], hosting.Watching]):
        self._where = where
        #: Asked each time rather than held: the gateway replaces what it is watching on every beat,
        #: and an object holding the first one would be answering into an adapter that has gone.
        self._hosted = hosted

    @property
    def where(self) -> Path:
        """The gateway's own log, for what runs alongside a turn. Read-only on purpose."""
        return self._where

    def hosted(self) -> hosting.Watching:
        """What the gateway is watching **now** — asked again every time, never held."""
        return self._hosted()

    def busy(self, agent: str, conversation: int) -> bool:
        """Whether a turn is already running in this conversation. **Asked of the kernel.**

        `hosting` publishes this question and cannot answer it — what a turn is lives here. It is
        asked before a message is marked, so that somebody typing again while their agent works is
        not given a mark for a turn that will never begin.

        `turns.busy` probes with a *shared* lock rather than an exclusive one, so two of these asked
        at the same moment do not each read the other as a running turn.
        """
        return turns.busy(agent, conversation)

    def remark(self, agent: str, kind: str, place: str, said: str) -> None:
        """One finished thing the agent said mid-turn, posted on its own (R-CH-19).

        **Plain, and deliberately.** No quote, because a thread where every line quotes the same
        message is unreadable; no cost line, because nothing has been settled to cost anything yet;
        and no mark, because marking a message done for each remark would say the turn finished
        several times. What makes the *last* one different is that `_delivered` sends it, and this
        does not.

        Split like anything else, because a brain can say something finished and enormous, and the
        adapter refuses what it is handed rather than cutting it.
        """
        with contextlib.suppress(Exception):
            pieces = delivery.split(said, at_most=self._at_most(agent, kind))
            if pieces:
                hosting.told(agent, self._where, self._hosted(), kind, place, pieces)

    def answer(self, agent: str, kind: str, place: str, who: str, body: str,
               external_id: Optional[str], landed: arriving.Landed) -> None:
        """Start a turn for this message and **return at once**. Never raises.

        A thread rather than the caller's, for the reason `hosting.Answering` gives. Daemon, because
        a gateway going down must not be held open by a turn — what settles that turn is the same
        thing that settles one killed outright, and it is the lock rather than this thread.
        """
        answering = threading.Thread(
            target=self._answered, name=f"answer-{kind}-{place}",
            args=(agent, kind, place, body, external_id, landed), daemon=True)
        answering.start()

    def _answered(self, agent: str, kind: str, place: str, body: str,
                  external_id: Optional[str], landed: arriving.Landed) -> None:
        """One turn for one message. **Never raises** — this is a thread, and nobody is above it.

        **`external_id` is carried the whole way down** — it is the platform's own name for the
        message somebody sent, and two separate things need it. The answer quotes it, so a reply
        reads as an answer rather than as a remark (R-DIS-28); and the mark that says how the turn
        ended goes on *that* message rather than nowhere (R-DIS-7). Both were built and neither
        fired, because this thread was started without it and every layer below defaulted it away.
        """
        try:
            for again in range(TRIES):
                try:
                    self._marked(agent, kind, place, WORKING)
                    watching = _Streaming(self, agent, kind, place)
                    got = turns.run(turns.Request(
                        agent=agent, prompt=body, conversation=landed.conversation,
                        trigger=instructions.A_PERSON_ASKED,
                        source=arriving.FROM_CHANNEL, place=place), watching=watching.heard)
                    self._delivered(agent, kind, place, got, external_id, watching.said_already)
                    self._marked(agent, kind, place,
                                 AS_A_STATE.get(got.turn_status, FAILED), external_id)
                    return
                except turns.Busy:
                    if turns.also_say(agent, landed.conversation, body):
                        # The agent is working and its brain reads while it works, so this reached
                        # the turn already going rather than waiting behind it. What it says next
                        # answers both, which is what somebody adding to their own question means.
                        _note(self._where, f"channel {kind}: {place} is being answered, so this "
                                           "was said into the turn already running")
                        return
                    # **Nobody took it, and that is not the same as nothing to do.** Either this
                    # brain reads nothing after its prompt, or the turn settled in the moment
                    # between the claim being refused and the word being offered. Both leave the
                    # message unanswered and this thread holding it, so it is asked again — the
                    # turn that was in the way is over or is ending, and the claim is about to be
                    # free. Bounded, because a conversation somebody is typing into steadily must
                    # not keep one thread here for ever.
                    if again + 1 < TRIES:
                        time.sleep(BEFORE_ASKING_AGAIN)
            _note(self._where, f"channel {kind}: {place} stayed busy, so this was recorded and "
                               "not answered", logs.ERROR)
            self._marked(agent, kind, place, FAILED, external_id)
        except Exception as why:                       # noqa: BLE001 — see the docstring
            _note(self._where, f"channel {kind}: answering {place} went wrong ({why})", logs.ERROR)
            with contextlib.suppress(Exception):
                self._marked(agent, kind, place, FAILED, external_id)

    def _delivered(self, agent: str, kind: str, place: str, got: turns.Outcome,
                   external_id: Optional[str] = None, said_already: bool = False) -> None:
        """The answer, cut to what this platform takes, with whatever the brain made beside it.

        **A turn that worked is never explained.** `protocol.has_answer` counts a file as an answer
        on purpose — something delivered is an answer even when nothing was typed about it — so a
        turn asked for a chart, which made the chart and said nothing, is a turn that succeeded. Read
        off the reply text alone, it fell through to the sentence for a turn that *failed*, and the
        person was sent "I could not answer that" with the chart attached to it.

        **This delivery is the answer, and says so** (R-DIS-28). `answering` carries the id of the
        message being replied to, which is how a surface tells the one message somebody was waiting
        for from the running commentary around it — and it is what a platform draws its own emphasis
        from, rather than anything this builds.

        **A turn somebody watched answers with its last thought, and one nobody watched with all of
        them** (R-CH-19). `protocol.last_thought` exists for exactly this and says so: a surface that
        was shown each finished remark as it landed has already had everything before the last one,
        so sending the whole reply posts every remark a second time — measured, and it read as the
        agent repeating itself. A turn with no remarks behind it is unchanged, because the reply and
        the last thought are the same thing when there was only ever one.
        """
        whole = got.last_thought if said_already and got.last_thought.strip() else got.reply
        # **A turn somebody stopped is never apologised for.** The sentence for a turn that produced
        # nothing exists because silence leaves a person unable to tell a broken agent from a slow
        # one — and somebody who has just pressed `/stop` knows exactly which this is. Told "I could
        # not answer that" for doing what they asked, the apology reads as a fault they caused.
        excused = got.worked or got.turn_status == kept.STOPPED
        said = whole.strip() or ("" if excused else self._instead(got))
        carrying = delivery.carried(agent, [str(one.get("at")) for one in got.files
                                            if one.get("at")])
        if not said and not carrying.files:
            return
        cost = self._cost(got)
        # **Room for the cost line is taken out of the limit before the words are cut, not after.**
        # The line goes above the answer on the piece that carries it, so a split done against the
        # whole limit hands the adapter a first piece that is exactly `max_text` and then grows it —
        # and the adapter refuses anything past the limit outright, as rundesk having failed to
        # split, which loses the delivery rather than trimming it. Taken off every piece rather than
        # only the first: it costs a few characters on the later ones and cannot be wrong.
        room = self._at_most(agent, kind) - (len(cost) + AROUND_THE_COST if cost else 0)
        pieces = delivery.split(said, at_most=max(1, room))
        hosting.told(agent, self._where, self._hosted(), kind, place, pieces,
                     sending=carrying.files, answering=external_id, cost=cost)

    def _cost(self, got: turns.Outcome) -> str:
        """What the turn cost, as one line — or nothing at all when nobody said.

        **A turn that reported no cost says nothing about it** (R-DIS-17), rather than a row of
        zeroes: `Usage.usage_reported` is the guard, and zero and unknown are different answers. The
        provider and the clock are still worth saying, because both are known whatever the brain
        reported — so a brain that counts nothing still shows which one answered and how long it
        took (R-DIS-24).
        """
        used = got.usage
        counted = used if used.usage_reported else protocol.Usage()
        return delivery.stats(provider=_named(got.provider_name),
                              input_tokens=counted.input_tokens,
                              output_tokens=counted.output_tokens,
                              cached_tokens=counted.cache_read_tokens,
                              context_tokens=counted.context_tokens,
                              elapsed=got.elapsed_seconds)

    def _instead(self, got: turns.Outcome) -> str:
        """What is said when a turn produced no answer at all.

        **Somebody is waiting, so silence is the one thing that must not happen.** A person who asked
        a question and received nothing cannot tell a broken agent from a slow one — and the closed
        vocabulary is what lets this say whether waiting will help without knowing a vendor's error
        strings.
        """
        if got.failure_code and protocol.needs_human_action(got.failure_code):
            return f"I could not answer, and this will not clear on its own: {got.failure_code}."
        if got.failure_code and protocol.is_retryable(got.failure_code):
            return f"I could not answer just now ({got.failure_code}). Asking again may work."
        return f"I could not answer that. {got.failure_message or ''}".strip()

    def _at_most(self, agent: str, kind: str) -> int:
        """How much this platform takes in one message, as the channel's own record says.

        Asked of the record rather than assumed, because it is the adapter that knows its platform —
        and defaulted where nothing said, so a channel whose adapter never declared one still gets an
        answer rather than nothing.
        """
        with contextlib.suppress(Exception):
            said = json.loads(channels_kept.one(agent, kind).get("settings") or "{}")
            at_most = said.get("max_text")
            if isinstance(at_most, int) and at_most > 0:
                return at_most
        return delivery.WHEN_UNSAID

    def _marked(self, agent: str, kind: str, place: str, state: str,
                external_id: Optional[str] = None) -> None:
        """Say what the turn is doing, in the words the channel layer renders. Never raises.

        **A mark needs the message it goes on** (R-DIS-7, R-DIS-8). Sent without one, every state
        crossed the seam correctly and the adapter had nothing to put a reaction on, so a turn was
        marked 👀 when it arrived and never marked again — which reads as an agent that took the
        message up and then forgot it. `working` is the exception and needs none: it is the typing
        indicator rather than a mark, and it belongs to the place rather than to one message.
        """
        hosting.marked(agent, self._where, self._hosted(), kind, place, state, external_id)


class _Streaming:
    """What a channel is shown while the turn is still running (R-CH-6, R-DIS-20).

    Handed to `turns.run` as `watching`, so it is called on the turn's own thread as each record
    arrives from the brain. **Nothing here may raise and nothing here may be slow**: the turn is the
    work and this is fidelity, and a brain held up by how fast a chat platform accepts writes is the
    trade nobody would make. Everything it does is guarded on the far side.

    ## Two different things go out, and they are not the same kind of thing

    **What the agent *did* is broad, counted, and disposable** — one closed word per tool, which the
    surface may collapse, edit in place and eventually drop. It is never the answer, so it never
    quotes anything and is never marked.

    **What the agent *said* is prose, and prose is only shown once it is finished** (R-CH-7). A brain
    that writes its reply a fragment at a time is shown nothing until the end, because a reply that
    rewrites itself in place is unreadable. A brain that says several *complete* things as it works
    has each posted the moment the **next** one arrives — which is what makes the last one the
    answer, and is only knowable once there is a next (R-CH-19). So a brain that never says `whole`
    produces exactly one message for the turn, and a chatty one produces a running transcript, from
    this same code.

    The held remark is deliberately never flushed here at the end. `_delivered` sends the reply the
    turn settled with, and that reply already contains it — flushing would post it twice, once as a
    remark and once as the answer.
    """

    def __init__(self, on: "OnAChannel", agent: str, kind: str, place: str) -> None:
        self._on = on
        self._agent = agent
        self._kind = kind
        self._place = place
        #: What each tool call said it was doing, by the brain's own id for it, so that the result
        #: coming back later can be named. Bounded because a long turn is thousands of tools and
        #: nothing removes an entry whose result never arrives.
        self._tools: Dict[str, Dict[str, str]] = {}
        #: The last finished thing the brain said, held until the next one proves it was not the end.
        self._said: Optional[str] = None
        #: Whether any remark was actually posted. **Read by `_delivered` to decide what the answer
        #: is**: a surface already shown everything before the last thought must be sent only that,
        #: or every remark arrives a second time inside the answer.
        self.said_already = False

    def heard(self, record: Dict[str, Any]) -> None:
        """One record from the brain. **Never raises** — a watcher is nobody's reason to fail."""
        with contextlib.suppress(Exception):
            said = record.get("type")
            if said == "tool":
                self._went_to_work(record)
            elif said == "result":
                self._came_back(record)
            elif said == "think":
                self._thought(record)
            elif said == "text" and record.get(protocol.WHOLE):
                self._remarked(record)

    def _went_to_work(self, record: Dict[str, Any]) -> None:
        """A tool was reached for. Shown by **what it did**, and skipped when the brain would not say.

        A brain doing something outside the closed set leaves the word out rather than stretching one
        to fit, so there is nothing here to show and showing nothing is the honest answer — a reader
        told nothing is better off than one taught to believe a word that means something else.
        """
        did = record.get("did")
        if did not in protocol.DID:
            return
        who = _a_helper(record.get("who")) if did == DELEGATE else ""
        given = str(record.get("id") or "")
        if given:
            self._remembered(given, did, who)
        self._doing(did, who=who)

    def _came_back(self, record: Dict[str, Any]) -> None:
        """What became of one tool — and **only when it is news**.

        A read that worked is already on the line that said it was reading, and saying so again
        doubles the length of every commentary to carry nothing. Two things are news: something that
        failed, and a subagent that finished — the second because a delegation is the one act that
        takes long enough that its ending is a separate event from its beginning.
        """
        known = self._tools.pop(str(record.get("id") or ""), None)
        if known is None:
            return
        did, who = known["did"], known["who"]
        if record.get("ok") is False:
            self._doing(did, ok=False, who=who)
        elif did == DELEGATE and record.get("ok") is True:
            self._doing(did, ok=True, who=who)

    def _thought(self, record: Dict[str, Any]) -> None:
        """The agent was thinking — **that it was, and never what about.**

        A thought is the most private thing a brain produces and the least useful to show: it is
        long, it is unedited, and it quotes whatever it has been reading. So it crosses as a bare
        activity record with no word on it at all, which the surface renders as its broad fallback.
        An empty one is not news and is dropped here, so a brain that emits a placeholder thought
        between every tool does not fill somebody's room with it.
        """
        if str(record.get("text") or "").strip():
            self._doing("")

    def _remarked(self, record: Dict[str, Any]) -> None:
        """A finished thing the brain said. Posts the **previous** one, and holds this."""
        said, self._said = self._said, str(record.get("text") or "")
        if said and said.strip():
            self.said_already = True
            self._on.remark(self._agent, self._kind, self._place, said)

    def _doing(self, did: str, ok: Optional[bool] = None, who: str = "") -> None:
        hosting.doing(self._agent, self._on.where, self._on.hosted(), self._kind, self._place,
                      did, ok=ok, who=who)

    def _remembered(self, given: str, did: str, who: str) -> None:
        """Keep what this tool was, bounded. Oldest first: a result that never came never will."""
        self._tools[given] = {"did": did, "who": who}
        while len(self._tools) > TOOLS_KEPT:
            self._tools.pop(next(iter(self._tools)))


class Gestures:
    """What a gesture from a person reaches — `hosting.Steering`, filled in (R-CAD-17, R-CAD-18).

    **Here rather than in `gateways`, and the layer table is why.** What a gesture needs is a turn's
    claim, a conversation's session, an agent's granted skills and its schedules — and `gateways` may
    reach none of `skills`. This package may reach all of them, so all but two of these are answered
    here and the two that are genuinely the *gateway's* are handed in: what its own state is, and how
    to ask it to end. A gesture is never a turn (R-CH-24), so nothing here takes minutes and it is
    safe to answer on the thread draining an adapter.

    Every answer is the words a person is shown, and `""` means *say nothing back* — which is what a
    control reported by the turn's own outcome does (R-DIS-12).
    """

    def __init__(self, where: Path, hosted: Callable[[], hosting.Watching],
                 wanted: Callable[[str], None], standing: Callable[[str], str]) -> None:
        self._where = where
        self._hosted = hosted
        #: How a gateway is asked to end. It cannot be ended from here: this runs on the thread
        #: draining an adapter's stdout, and a gateway torn down from there would unwind the stack
        #: out from under the loop that owns it.
        self._wanted = wanted
        #: What `/status` says. The gateway's own, because only it knows what it is.
        self._standing = standing

    def controlled(self, agent: str, kind: str, place: str, who: str, control: str) -> str:
        if control == hosting.FORGET:
            return self._forgotten(agent, place)
        if control == hosting.STOP:
            return self._stopped(agent, place)
        # **Announced before it happens, because the thing that would report it afterwards is the
        # thing going away.**
        self._wanted(control)
        return ("♻️ Restarting — I'll be back in a moment." if control == hosting.RESTART
                else "🛑 Shutting down. Nothing here can start me again.")

    def asked(self, agent: str, who: str, query: str) -> str:
        if query == hosting.STATUS:
            return self._standing(agent)
        if query == hosting.VERSION:
            return f"rundesk {__version__}"
        if query == hosting.SKILLS:
            return _what_it_holds(agent)
        if query == hosting.SCHEDULES:
            return _what_is_coming(agent)
        return ""

    def configured(self, agent: str, kind: str, place: str, who: str, provider: str) -> str:
        """Change which brain answers for this agent (R-CH-26, R-DIS-25).

        **Only where the channel allows exactly one person, and only that person.** A provider is an
        agent-wide default: it decides what every conversation, every other channel and every
        schedule this agent has will run on. Being on a shared room's allow list is authority to
        speak to the agent there, and it is not authority to change what the agent *is* for
        everybody — so the narrower question is asked here rather than reusing the one that let
        somebody in.

        **The session takes care of itself.** A handle is kept per conversation *and per brain*, so
        a conversation that moves to a different provider has no handle on it and starts fresh
        without anything being deleted. Nothing is thrown away either: moving back finds the old
        conversation exactly where it was left.
        """
        wanted = provider.strip()
        if not wanted:
            return "Say which brain — for example **/provider codex**."
        allowed = self._only_one(agent, kind)
        if allowed is None or allowed != who:
            return ("Changing the brain is an agent-wide decision, so it can only be done on a "
                    "channel that one person uses.")
        try:
            adapters.where(wanted)
        except Exception:                              # noqa: BLE001 — see below
            # **Refused before anything is written**, and named against what this install has. A
            # default nothing stands behind is an agent whose every turn fails from the next message
            # on, and the person who typed it would be the last to find out.
            known = ", ".join(f"**{one}**" for one in adapters.known()) or "none"
            return f"There is no brain called **{wanted}**. This install has: {known}."
        settled = records.read(directory.records(agent))
        if str(settled.get("provider_name") or "") == wanted:
            return f"**{agent}** already answers on **{wanted}**."
        records.stated(directory.records(agent), {"provider_name": wanted})
        return (f"🧠 **{agent}** now answers on **{wanted}**. This conversation starts fresh on it — "
                f"and whatever it had on the old brain is still there if you move back.")

    def _only_one(self, agent: str, kind: str) -> Optional[str]:
        """The single person this channel allows, or `None` where it allows any other number."""
        with contextlib.suppress(Exception):
            allowed = channels_kept.who_may_reach(channels_kept.one(agent, kind))
            if len(allowed) == 1:
                return str(allowed[0])
        return None

    def _forgotten(self, agent: str, place: str) -> str:
        """Start this conversation fresh, so the next message begins a new session (R-CH-10).

        **The session goes and the turn running is not touched.** A turn already going writes down
        where it got to when it ends, and that lands *after* this — so forgetting mid-turn was undone
        a few seconds later by the very turn it deliberately did not interrupt. Said to the person
        instead, because what they asked for still happens, to the next message.
        """
        found = arriving.standing_in(agent, place)
        if found is None:
            return "🧹 Nothing said here yet — the next message starts fresh anyway."
        kept.forget_sessions(agent, found)
        if turns.busy(agent, found):
            return ("🧹 The next message starts fresh. A turn is still running, and what it says "
                    "will be the last of the old conversation.")
        return "🧹 Started fresh. The next message begins a new session."

    def _stopped(self, agent: str, place: str) -> str:
        """End the turn running in this conversation (R-CH-9)."""
        found = arriving.standing_in(agent, place)
        if found is None or not turns.busy(agent, found):
            return "✋ Nothing is running here."
        if turns.stop(agent, found):
            return "✋ Stopped."
        # Busy, and not by anything this process is running — a scheduled turn takes a process of
        # its own. Said as what it is rather than as a failure, because trying again will not help.
        return "✋ Something is running here, but not something I can stop from a conversation."


def _what_it_holds(agent: str) -> str:
    """The skills this agent was granted, one to a line and sorted (R-DIS-36).

    **This agent's, and never the library's.** What an install *has* is a different question from
    what this agent may use, and answering the first here would list somebody else's tools in
    somebody's room.
    """
    try:
        held = sorted(one.name for one in grants.held(agent))
    except Exception as why:                           # noqa: BLE001 — an inspection boundary
        return f"I could not read my skills ({type(why).__name__})."
    if not held:
        return f"**{agent}** holds no skills."
    return "\n".join([f"**{agent} holds {len(held)} skill{'s' if len(held) != 1 else ''}:**"]
                     + [f"- {one}" for one in held])


def _what_is_coming(agent: str) -> str:
    """The schedules that can still run, soonest first (R-DIS-37).

    **What can still run**, rather than everything ever written down: one whose moment has gone is
    not something anybody is deciding about, and a list carrying them would bury the two that matter
    under a year of history. One nobody could understand is named rather than dropped, because a
    schedule missing from a list reads as a schedule that is not there.
    """
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        read, trouble = due.read(schedules_kept.all(agent))
        coming = [one for one in read if not due.expired(one, now)]
        coming.sort(key=lambda one: (due.next_after(one, now) is None,
                                     due.next_after(one, now) or now))
    except Exception as why:                           # noqa: BLE001 — an inspection boundary
        return f"I could not read my schedules ({type(why).__name__})."
    if not coming and not trouble:
        return f"**{agent}** has nothing left to run."
    said = [f"**{agent} has {len(coming)} schedule{'s' if len(coming) != 1 else ''}:**"]
    said += [f"- {one.name} — {due.describe(one, now)}" for one in coming]
    said += [f"- {name} — could not be read" for name, _why in trouble]
    return "\n".join(said)


class OnASchedule:
    """Starts a scheduled turn as a process of its own. Handed to `firing.looked` as `asking`.

    `firing` wants a pid back and hands out the lock descriptor it is holding, so that a schedule's
    claim survives the gateway that started it — the kernel drops it when the child tree ends,
    however that happens. A turn run on this process's own thread could not offer that.
    """

    def start(self, one: due.Schedule, agent: str, holding: int) -> int:
        """Start `rundesk providers run` for this schedule and hand back its pid."""
        return programs.start(
            argv=[the_command(), *THE_RUNNER, agent, "--schedule", one.name],
            log=firing.output_of(agent, one.name),
            where=directory.home(agent),
            env=firing.the_environment(),
            holding=(holding,))


def for_a_schedule(agent: str, schedule: str, when=None) -> turns.Outcome:
    """Take one scheduled turn, here, in this process. What `rundesk providers run` calls.

    Its own conversation, keyed by the schedule's name, so **a run at three in the morning never
    lands in the exchange somebody is typing into** — which is what happened in the build this
    replaces: a scheduled turn resumed the owner's own session and left its prompt and its answer in
    the middle of it.
    """
    row = schedules_kept.one(agent, schedule)
    said = due.understood(row)
    if not (said.prompt or "").strip():
        raise Refused(f"{schedule} does not ask {agent} anything — it names a program to start, "
                      f"which is `rundesk schedules run {agent} {schedule}`")
    landed = arriving.recorded_for_a_schedule(agent, schedule, said.prompt)
    return turns.run(turns.Request(
        agent=agent, prompt=said.prompt, conversation=landed.conversation,
        trigger=instructions.A_SCHEDULE_CAME_DUE, schedule_id=row.get("id"),
        model_name=said.model, source=arriving.FROM_SCHEDULE, place=schedule))


def the_command() -> str:
    """The `rundesk` a scheduled turn is started with. **This install's, never another's.**

    One line, because the question is `core.config`'s and an agent running `rundesk` from inside its
    own turn has to reach the same one. Two answers to *where is rundesk* is the split `firing`
    records as having "silently split the machine in two".
    """
    return config.the_command()


def _a_helper(said: Any) -> str:
    """One safe, compact name for a subagent — **never its location, and never its own line.**

    Two separate hazards in one short string, and the build this replaces met both. A helper is
    named by whoever wrote it, so the name may be an absolute path, and posting that publishes the
    machine's layout into a room — the last component only, for the reason `_named` gives. And it is
    a stranger's text arriving on a line of running commentary, so a newline in it is somebody
    ending our sentence and starting one of their own.
    """
    named = str(said or "").strip().replace("\\", "/").rsplit("/", 1)[-1]
    return " ".join(named.split())[:A_HELPER_AT_MOST]


def _named(provider: str) -> str:
    """What to call a brain out loud, **without saying where it lives** (R-CH-28).

    A provider is resolved the way an adapter is: a bare name is one this install ships, and anything
    with a path separator in it is a path somebody gave. That second kind is an absolute path to a
    file on this machine, and a cost line goes into a chat room — so putting the resolved name
    straight into one publishes the owner's directory layout, their username with it, to everybody
    who can read the channel. Caught by a case whose stand-in brain is referred to by path, which is
    the ordinary shape of a provider somebody wrote themselves.

    The last component and nothing else. Never rewritten into something prettier: this is the name in
    the turn's own record, and a surface that showed a different word could not be matched back to it.
    """
    return PurePosixPath(provider).name if "/" in provider else provider


def _note(where: Path, said: str, level: str = logs.INFO) -> None:
    """One line in the gateway's own log, and never a reason to end anything."""
    with contextlib.suppress(Exception):
        if where.parent.is_dir():
            logs.note(where, said, level)
