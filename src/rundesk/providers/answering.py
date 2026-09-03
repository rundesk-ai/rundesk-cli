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
import stat
import threading
import time
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict, List, Optional, Tuple

from rundesk import __version__
from rundesk.agents import directory, records
from rundesk.channels import adapters as channels_adapters
from rundesk.channels import arriving, delivery, hosting
from rundesk.channels import kept as channels_kept
from rundesk.core import config, paths
from rundesk.providers import accounts, adapters, continuations, instructions, kept, protocol, turns
from rundesk.schedules import due, firing
from rundesk.schedules import kept as schedules_kept
from rundesk.skills import grants
from rundesk.utils import locking, logs, programs

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

#: What a surface that shows the answer alone is given when a turn completed and closed without
#: saying anything after its last tool call. **A fact and nothing more.** It does not say the work
#: succeeded, because this does not know; it does not say it failed, because it did not; and it says
#: nothing about what the tools did, which is the part a person would most like invented for them.
#: A surface that shows a turn as it happens needs none of this — the person watched it — and a
#: stopped turn is not given it either, because somebody who pressed `/stop` knows why it is quiet.
NOTHING_CLOSING = "This turn finished without a final answer."


#: How long an answer waits to find out whether its platform took it, before the turn is settled.
#:
#: **This is what stands between a refused delivery and a ✅ on the question it answered.** The mark
#: is composed from the turn's own outcome, and a turn whose answer nobody can see did not do what
#: the mark would say it did — so the outcome has to know, and knowing costs one platform round trip
#: on the one delivery a person is actually waiting for.
#:
#: Generous against a round trip and short against somebody watching a thread: an adapter that has
#: not answered inside this is one whose delivery is treated as landed, because **an adapter is free
#: to acknowledge nothing at all** and silence must never become a failure. What this bounds is how
#: long a turn waits to hear bad news, never whether it settles.
LANDS_WITHIN = 10.0

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

#: Pending delegation words placed into one provider turn. At least the oldest whole message is
#: always kept, even if that one exceeds this soft aggregate bound; later guidance remains pending
#: for the next turn rather than being clipped or reordered.
DELEGATED_PROMPT_AT_MOST = turns.DELEGATED_PROMPT_AT_MOST

#: Pending messages one delegated turn may claim. This is also a bound on the ids handed to one
#: SQLite `UPDATE`; keeping it far below every supported SQLite variable ceiling means many tiny
#: guidance messages cannot make the claim itself fail. The rest stay pending for the next turn.
DELEGATED_MESSAGES_AT_MOST = turns.DELEGATED_MESSAGES_AT_MOST

#: Pending inbound channel messages one stop may settle in a conversation. The exact ids become one
#: atomic `UPDATE`, so this stays far below every supported SQLite variable ceiling.
#:
#: **A bound on what is marked, never on what is stopped.** They are taken from the newest end, and
#: claiming the newest unclaimed row supersedes every older one — so a conversation holding more
#: than this keeps rows nothing will ever run rather than rows a later sweep would start, and the
#: word a person is given stays true. See `Gestures._stopped`.
PENDING_STOPPED_AT_MOST = turns.DELEGATED_MESSAGES_AT_MOST


#: How many times a message that found the conversation busy is offered again.
#:
#: **Not a retry of something that failed** — nothing failed. It is what a message does when the
#: turn it tried to join ended in the moment between being refused the claim and being offered as a
#: word: the way in has closed and the way round has opened, and asking once more takes it. Three,
#: because each attempt needs the one before it to have genuinely settled, and a conversation that
#: is busy three times over is one somebody is typing into faster than their agent can answer.
#: What an agent is shown when work it handed over comes back. **Its words, verbatim and labelled
#: unchecked** — rundesk summarises nothing and asserts nothing about them, which is the strongest
#: idea carried over from the previous build. What follows is the one instruction that matters: this
#: has not been checked, and nobody has been told anything yet.
REVIEW = """{agent} returned this unchecked delegated result; nobody has received it onward.

{provenance}

{answer}

Verify material claims before using or reporting them."""


def _delegation_provenance(answer: str) -> str:
    """Requested, effective-admission and actual terminal provider/model evidence."""
    requested_provider = getattr(answer, "requested_provider_name", None)
    requested_alias = getattr(answer, "requested_provider_alias", None)
    requested_model = getattr(answer, "requested_model_name", None)
    effective_provider = getattr(answer, "effective_provider_name", None)
    effective_alias = getattr(answer, "effective_provider_alias", None)
    effective_model = getattr(answer, "effective_model_name", None)
    provider = getattr(answer, "provider_name", None)
    alias = getattr(answer, "provider_alias", None)
    model = getattr(answer, "model_name", None)
    requested = _requested_provider_name(str(requested_provider)) if requested_provider else "none"
    if requested_alias:
        requested += f" ({_metadata_name(str(requested_alias))})"
    if requested_model:
        requested += f" / {_metadata_name(str(requested_model))}"
    effective = _named(str(effective_provider)) if effective_provider else "legacy late-bound"
    if effective_alias:
        effective += f" ({_metadata_name(str(effective_alias))})"
    if effective_model:
        effective += f" / {_metadata_name(str(effective_model))}"
    elif effective_provider:
        effective += " / provider default"
    actual = _named(str(provider)) if provider else "not recorded"
    if alias:
        actual += f" ({_metadata_name(str(alias))})"
    if model:
        actual += f" / {_metadata_name(str(model))}"
    return (f"Provider/model — requested: {requested}; effective at admission: {effective}; "
            f"terminal turn: {actual}.")


TRIES = 3

#: How long to wait before offering a refused message again. Long enough for a turn that was
#: settling to have settled and let go of the claim, short enough that somebody watching a room does
#: not see their message sit there.
BEFORE_ASKING_AGAIN = 0.25

#: How long collection waits for a review worker to prove that a live or newly started turn claimed
#: its durable result. This is admission, not completion; an idle turn reaches it before its brain
#: starts, and an external busy turn refuses it on the ordinary bounded retry path.
REVIEW_ADMITTED_WITHIN = 2.0


class Refused(Exception):
    """A schedule that asks nobody anything, asked to take a turn.

    Named rather than answered as a sentence, because the caller is a command that has to exit
    non-zero and say what to type instead.
    """


#: What a schedule's turn is started with. `rundesk` itself, because a schedule's program may be
#: rundesk and `firing` already carries `RUNDESK_HOME` for exactly that.
THE_RUNNER = ("providers", "run")


class IntoAChannel:
    """Getting an agent's words onto the platform its conversation stands on.

    **One door out, and two tenants leave through it.** A message a person sent and an answer another
    agent handed back are different work, and what happens once a turn has settled is the same work
    exactly: cut the reply to what the platform takes, attach whatever the brain made, put the cost on
    it, and hand it to the adapter. Written twice, it was written once — and the half that was never
    written is why a delegated answer reached a person's records and never their room.

    Holds nothing but what it needs to find the gateway's own log and to reach the adapter again.
    """

    def __init__(self, where: Path, hosted: Callable[[], hosting.Watching]):
        self._where = where
        #: Asked each time rather than held: the gateway replaces what it is watching on every beat,
        #: and an object holding the first one would be answering into an adapter that has gone.
        self._hosted = hosted
        #: Whether each surface shows a turn as it happens, by adapter kind. Asked of the adapter
        #: once for the life of this gateway and remembered: it is a fact about the program on disk,
        #: not about a turn, and asking it per answer would run that program for every reply.
        self._as_it_happens: Dict[str, bool] = {}
        self._asking = threading.Lock()

    @property
    def where(self) -> Path:
        """The gateway's own log, for what runs alongside a turn. Read-only on purpose."""
        return self._where

    def streaming(self, kind: str) -> bool:
        """Whether this surface shows a turn while it runs, from the adapter's own declaration.

        **The composition of an answer depends on it, so it is asked and never assumed.** A surface
        that shows working commentary has already shown everything the brain said before its last
        thought, so its answer is that last thought alone; a surface that shows nothing until the
        end has shown none of it, so its answer is everything the brain said. Read the wrong way
        round, the second kind loses every thought but the last — which is what a brain that says
        several finished things after going to work produces, and two shipped providers do.

        **`stream` is the adapter's word for it** and `--capabilities` is where an adapter says so,
        offline and with no account. Unsaid means *shows it as it happens*: that is what every
        surface did before this question was asked, and a third-party adapter that has never heard
        of the field keeps the behaviour it was written against.

        Asked once per kind for the life of this gateway. The program on disk does not change under
        a running gateway, and an update replaces the gateway with it.
        """
        with self._asking:
            if kind not in self._as_it_happens:
                said = True
                with contextlib.suppress(Exception):
                    declared = channels_adapters.capabilities(kind).get("stream", True)
                    said = bool(declared)
                self._as_it_happens[kind] = said
            return self._as_it_happens[kind]

    def hosted(self) -> hosting.Watching:
        """What the gateway is watching **now** — asked again every time, never held."""
        return self._hosted()

    def remark(self, agent: str, kind: str, place: str, said: str) -> None:
        """One finished thing the agent said mid-turn, posted on its own (R-CH-19).

        **Plain, and deliberately.** No quote, because a thread where every line quotes the same
        message is unreadable; no cost line, because nothing has been settled to cost anything yet;
        and no mark, because marking a message done for each remark would say the turn finished
        several times. What makes the *last* one different is that `_delivered` sends it, and this
        does not.

        Split like anything else, because a brain can say something finished and enormous, and the
        adapter refuses what it is handed rather than cutting it.

        **Marked `remark` on the way out, and this is the only place that knows to.** What a brain
        said before its answer and the answer itself are both prose it wrote, so a surface handed
        the two cannot tell them apart — and one whose whole shape is *the answer and nothing else*
        posted both, which is one question answered twice. The phase is known here, so it is said
        here rather than guessed at the far end.
        """
        with contextlib.suppress(Exception):
            pieces = delivery.split(said, at_most=self._at_most(agent, kind))
            if pieces:
                hosting.told(agent, self._where, self._hosted(), kind, place, pieces, remark=True)

    def _delivered(self, agent: str, kind: str, place: str, got: turns.Outcome,
                   external_id: Optional[str] = None,
                   linked_earlier: Tuple[str, ...] = (), notice: bool = False) -> str:
        """The answer, cut to what this platform takes, with whatever the brain made beside it.

        **Hands back why the platform would not take it, or `""`.** A turn whose answer was refused
        is not a turn somebody can read the answer to, and the mark that says what became of it is
        composed one line later — so this waits `LANDS_WITHIN` for the adapter to answer, and says
        what it heard. `""` covers both *it landed* and *nobody said*, which is deliberate: an
        adapter may acknowledge nothing, and only an explicit refusal is news.

        **A turn that worked is never explained.** `protocol.has_answer` counts a file as an answer
        on purpose — something delivered is an answer even when nothing was typed about it — so a
        turn asked for a chart, which made the chart and said nothing, is a turn that succeeded. Read
        off the reply text alone, it fell through to the sentence for a turn that *failed*, and the
        person was sent "I could not answer that" with the chart attached to it.

        **This delivery is the answer, and says so** (R-DIS-28). `answering` carries the id of the
        message being replied to, which is how a surface tells the one message somebody was waiting
        for from the running commentary around it — and it is what a platform draws its own emphasis
        from, rather than anything this builds.

        **A channel turn answers with one final thought** (R-CH-19). Earlier working remarks were
        already shown as they landed. An explicit final produced before later guidance is a
        candidate that the later final supersedes, not another completed answer to post.
        """
        # **A channel turn has one final answer, and what that is depends on what the surface has
        # already shown** (R-CH-19, R-CAD-27). Where working commentary went out as it was finished,
        # the answer is the last thought and the rest is already on the platform.
        #
        # Where nothing goes out until the end, the answer is the closing response: every finished
        # thought after the last tool call, and no earlier one. Both halves of that are load-bearing
        # — a brain that says three finished things after going to work and marks none of them final
        # has two of them dropped by anything that reads only the last, and `reply` in its place
        # carries the narration it said before and between its tools into the one message a quiet
        # surface posts. There is no fallback to `reply` here for the same reason.
        if self.streaming(kind):
            whole = got.last_thought if got.last_thought.strip() else got.reply
        else:
            whole = got.closing_response
        # **A completion mark and nothing beside it is not an answer.** Where a turn completed and
        # closed without a word after its last tool call, a surface showing the answer alone has
        # nothing at all to show: the person sees ✅ against their question and no reply, which reads
        # as an answer they cannot find rather than as one that was never made. A surface that shows
        # a turn as it happens is unaffected — the person watched the working — and a stopped turn
        # keeps the silence below, which is the one case where nothing is the honest answer.
        if (not whole.strip() and not self.streaming(kind)
                and got.worked and got.turn_status != kept.STOPPED):
            whole = NOTHING_CLOSING
        # **A turn somebody stopped is never apologised for.** The sentence for a turn that produced
        # nothing exists because silence leaves a person unable to tell a broken agent from a slow
        # one — and somebody who has just pressed `/stop` knows exactly which this is. Told "I could
        # not answer that" for doing what they asked, the apology reads as a fault they caused.
        excused = got.worked or got.turn_status == kept.STOPPED
        said = whole.strip() or ("" if excused else self._instead(got))
        # **A brain says *send this* by linking it, because that is the one place the intent exists**
        # (R-CH-31), because a stream says which files were *touched* and never which one was made
        # for the person who asked. So the links come out of the answer, the paths go through the
        # same approval as anything else, and what is left in the words is the label alone — never
        # the owner's own directory, posted into a room.
        #
        # **One tool is the exception, and an adapter that can see it now reports one**: generating
        # an image makes exactly one file, it exists only because somebody asked for it, and it
        # lands under the brain's own session directory where nobody would look for it. Both sources
        # are merged before approval, which is why nothing here had to change to accept it.
        prepared = delivery.prepared(
            said, [*linked_earlier, *(str(one.get("at")) for one in got.files
                                      if one.get("at"))])
        said = prepared.text.strip()
        # **What could not be sent is said, never dropped.** `delivery.carried` computes a sentence
        # for every file it turns away — unreadable, too big, past the ten — and until
        # this read it, the whole of what happened to one was that it did not arrive. A person
        # expecting a file and told nothing cannot tell that from an agent that made none.
        for why in prepared.refused:
            _note(self._where, f"channel {kind}: {why}", logs.WARNING)
        if not said and not prepared.files:
            return ""
        cost = self._cost(got)
        # **Room for the cost line is taken out of the limit before the words are cut, not after.**
        # The line goes above the answer on the piece that carries it, so a split done against the
        # whole limit hands the adapter a first piece that is exactly `max_text` and then grows it —
        # and the adapter refuses anything past the limit outright, as rundesk having failed to
        # split, which loses the delivery rather than trimming it. Taken off every piece rather than
        # only the first: it costs a few characters on the later ones and cannot be wrong.
        room = self._at_most(agent, kind) - (len(cost) + AROUND_THE_COST if cost else 0)
        pieces = delivery.split(said, at_most=max(1, room))
        turned_away: List[str] = []
        wrote = hosting.told(agent, self._where, self._hosted(), kind, place, pieces,
                             sending=prepared.files, answering=external_id, cost=cost,
                             landed_within=LANDS_WITHIN, refusals=turned_away, notice=notice)
        if not wrote:
            # Nothing was hosting this channel by the time the answer was ready. The words exist in
            # the agent's own records either way; what does not exist is anywhere a person can read
            # them, which is the same news as a refusal and is said as one.
            return "there was no channel to answer through"
        return turned_away[0] if turned_away else ""

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
        return delivery.stats(provider=_shown_provider(got.provider_name, got.provider_alias),
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


class OnAChannel(IntoAChannel):
    """Answers a message that arrived on a channel, on a thread of its own.

    Handed to `hosting.looked`. Holds nothing but what it needs to find the gateway's own log and to
    reach the adapter again with the answer — the turn itself keeps no state here, because a turn
    that outlived the object that started it would be a turn nobody could settle.
    """

    def __init__(self, where: Path, hosted: Callable[[], hosting.Watching]):
        super().__init__(where, hosted)
        self._answering_messages = set()
        self._pending_failures = set()
        self._answering_lock = threading.Lock()

    def busy(self, agent: str, conversation: int) -> bool:
        """Whether a turn is already running in this conversation. **Asked of the kernel.**

        `hosting` publishes this question and cannot answer it — what a turn is lives here. It is
        asked before a message is marked, so that somebody typing again while their agent works is
        not given a mark for a turn that will never begin.

        `turns.busy` probes with a *shared* lock rather than an exclusive one, so two of these asked
        at the same moment do not each read the other as a running turn.
        """
        return turns.busy(agent, conversation)

    def answer(self, agent: str, kind: str, place: str, who: str, body: str,
               external_id: Optional[str], landed: arriving.Landed) -> bool:
        """Start a turn for this message and **return at once**. Never raises.

        A thread rather than the caller's, for the reason `hosting.Answering` gives. Daemon, because
        a gateway going down must not be held open by a turn — what settles that turn is the same
        thing that settles one killed outright, and it is the lock rather than this thread.
        """
        key = (agent, landed.message)
        with self._answering_lock:
            if key in self._answering_messages or key in self._pending_failures:
                return False
            self._answering_messages.add(key)
        answering = threading.Thread(
            target=self._answered_once, name=f"answer-{kind}-{place}",
            args=(agent, kind, place, body, external_id, landed), daemon=True)
        answering.start()
        return True

    def _answered_once(self, agent: str, kind: str, place: str, body: str,
                       external_id: Optional[str], landed: arriving.Landed) -> None:
        try:
            self._answered(agent, kind, place, body, external_id, landed)
        finally:
            with self._answering_lock:
                self._answering_messages.discard((agent, landed.message))

    def _do_not_repeat_pending(self, agent: str, message: int) -> None:
        """Suppress one pre-admission failure until a replacement gateway can retry it."""
        with self._answering_lock:
            self._pending_failures.add((agent, message))

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
                        situation=instructions.USER_TO_AGENT,
                        source=arriving.FROM_CHANNEL, place=place,
                        inbound_messages=(landed.message,)), watching=watching.heard,
                        # The final attempt waits on the kernel's conversation claim. This thread
                        # owns the durable channel message, and without a later gateway sweep it is
                        # the one place that can guarantee an external active turn is followed by
                        # exactly one fallback turn rather than an orphaned pending row.
                        waiting=again + 1 == TRIES)
                    refused = self._delivered(
                        agent, kind, place, got, external_id, tuple(watching.linked))
                    # **One producer of the mark, and this is still it.** Turning the adapter's
                    # acknowledgement into a mark of its own was removed once and must stay removed
                    # — two producers raced and the mark a person saw was whichever record arrived
                    # last. What changed is that the outcome now includes whether the answer reached
                    # anybody, which is a fact about this turn and not a second opinion about it.
                    became = AS_A_STATE.get(got.turn_status, FAILED)
                    if refused:
                        _note(self._where, f"channel {kind}: the answer to {place} was not "
                                           f"delivered — {refused}", logs.ERROR)
                        became = FAILED
                    self._marked(agent, kind, place, became, external_id)
                    return
                except turns.Busy:
                    admission = turns.Admission()
                    if turns.also_say(
                            agent, landed.conversation, body, (landed.message,), admission):
                        if admission.wait() is not True:
                            continue
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
            _note(self._where, f"channel {kind}: {place} stayed busy; the message remains "
                               "pending for a later gateway sweep", logs.WARNING)
        except locking.Stuck as why:
            # An update closes work admission before gateways stop. A message already read from
            # the adapter must stay unclaimed so the restarted gateway can recover it, rather than
            # looking failed merely because it arrived during that short barrier.
            _note(self._where, f"channel {kind}: admission stayed busy while answering {place} "
                               f"({why}); the message remains pending for retry", logs.WARNING)
            self._do_not_repeat_pending(agent, landed.message)
            # **The indicator this thread put up is this thread's to take down** (R-CH-37).
            # `working` is sent before admission is asked for, so a refusal here left a place
            # typing with no turn behind it — for ever, because this message is now suppressed
            # and nothing else in this gateway would ever send a state for it. Sent without the
            # message's id on purpose: the message is still pending, and a mark on it would say the
            # turn it is waiting for had settled. Left alone where this gateway is already running a
            # turn in the same conversation, because that turn owns the indicator and ends it itself.
            if not turns.running_here(agent, landed.conversation):
                self._marked(agent, kind, place, FAILED)
        except Exception as why:                       # noqa: BLE001 — see the docstring
            _note(self._where, f"channel {kind}: answering {place} went wrong ({why})", logs.ERROR)
            self._do_not_repeat_pending(agent, landed.message)
            with contextlib.suppress(Exception):
                self._marked(agent, kind, place, FAILED, external_id)

    def _marked(self, agent: str, kind: str, place: str, state: str,
                external_id: Optional[str] = None) -> None:
        """Say what the turn is doing, in the words the channel layer renders. Never raises.

        **A message mark needs the message it goes on** (R-DIS-7, R-DIS-8). Sent without one, every
        state crossed the seam correctly and the adapter had nothing to put a reaction on. `working`
        needs none because it is the place's typing indicator. A terminal state also omits the
        message when admission failed before a turn existed: it ends that indicator without marking
        the still-pending message.
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
    this same code. An explicit `final` is held as an answer candidate and never posted as working
    commentary; later steering may supersede it with another explicit final.

    The held remark is deliberately never flushed here at the end. `_delivered` sends the reply the
    turn settled with, and that reply already contains it — flushing would post it twice, once as a
    remark and once as the answer.
    """

    def __init__(self, on: "IntoAChannel", agent: str, kind: str, place: str) -> None:
        self._on = on
        self._agent = agent
        self._kind = kind
        self._place = place
        #: What each tool call said it was doing, by the brain's own id for it, so that the result
        #: coming back later can be named. Bounded because a long turn is thousands of tools and
        #: nothing removes an entry whose result never arrives.
        self._tools: Dict[str, Dict[str, str]] = {}
        #: The last finished thing the brain said, held until the next one proves it was not the end.
        self._said: Optional[Tuple[str, bool]] = None
        #: Local files explicitly declared in remarks already shown. They are held for the final
        #: delivery: a path must never leak mid-turn, and an attachment belongs with the answer.
        self.linked: List[str] = []

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
        previous = self._said
        self._said = (str(record.get("text") or ""), record.get("final") is True)
        # An explicit final is a candidate answer, never working commentary. If steering makes the
        # provider produce another final, the old one is superseded rather than posted as a second
        # apparent answer.
        if previous and not previous[1] and previous[0].strip():
            shown, linked = delivery.declared_in(previous[0])
            # **Collected whether or not it is posted.** A file the brain declared in a thought is
            # declared however that thought reaches somebody, and a surface that shows the answer
            # alone still sends the file with it.
            self.linked.extend(linked)
            if self._on.streaming(self._kind):
                self._on.remark(self._agent, self._kind, self._place, shown)

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
                 wanted: Callable[[str], None], standing: Callable[[str], str],
                 delegations: Optional[Callable[[str, str, str], str]] = None) -> None:
        self._where = where
        self._hosted = hosted
        #: How a gateway is asked to end. It cannot be ended from here: this runs on the thread
        #: draining an adapter's stdout, and a gateway torn down from there would unwind the stack
        #: out from under the loop that owns it.
        self._wanted = wanted
        #: What `/status` says. The gateway's own, because only it knows what it is.
        self._standing = standing
        #: The cross-store read belongs to the gateway layer. Passed in so providers need not reach
        #: up to it and a gesture remains drivable with no gateway or durable delegation fixture.
        self._delegations = delegations

    def controlled(self, agent: str, kind: str, place: str, who: str, control: str) -> str:
        if control == hosting.FORGET:
            return self._forgotten(agent, place)
        if control == hosting.STOP:
            return self._stopped(agent, kind, place)
        # **Announced before it happens, because the thing that would report it afterwards is the
        # thing going away.**
        self._wanted(control)
        return ("♻️ Restarting — I'll be back in a moment." if control == hosting.RESTART
                else "🛑 Shutting down. Nothing here can start me again.")

    def asked(self, agent: str, kind: str, place: str, who: str, query: str) -> str:
        if query == hosting.STATUS:
            return self._standing(agent)
        if query == hosting.VERSION:
            return f"rundesk {__version__}"
        if query == hosting.AGENTS:
            return _what_agents_are()
        if query == hosting.SKILLS:
            return _what_it_holds(agent)
        if query == hosting.SCHEDULES:
            return _what_is_coming(agent)
        if query == hosting.DELEGATIONS and self._delegations is not None:
            return self._delegations(agent, kind, place)
        return ""

    def configured(self, agent: str, kind: str, place: str, who: str, provider: str,
                   alias: Optional[str] = None) -> str:
        """Change which brain answers for this agent (R-CH-26, R-DIS-25).

        **Only where the channel allows exactly one person, and only that person.** A provider is an
        agent-wide default: it decides what every conversation, every other channel and every
        schedule this agent has will run on. Being on a shared room's allow list is authority to
        speak to the agent there, and it is not authority to change what the agent *is* for
        everybody — so the narrower question is asked here rather than reusing the one that let
        somebody in.

        **Every handle this conversation holds is thrown away, on every brain.** Keying sessions by
        conversation *and* brain already makes the move itself fresh — the new one has no handle to
        resume — but it leaves the old one sitting there, so moving back would silently pick up a
        conversation from before the change. A person who changed brain and changed back has started
        again twice as far as they are concerned, and an agent resuming a thread from two providers
        ago is the opposite of what either of those asked for.
        """
        wanted = provider.strip()
        wanted_alias = alias.strip() if alias is not None else None
        if alias is not None and not wanted_alias:
            return "An account alias cannot be blank; omit it to use the provider default."
        if not wanted:
            # **Named off what this install actually has**, never a brand written down here. Two
            # reasons and both matter: nothing under `providers/` may know a vendor's name — the
            # seam is what makes a brain replaceable, and a module that named one would be the
            # first place to stop being true — and an example naming a brain this machine cannot
            # run is advice that fails the moment somebody takes it.
            here = adapters.known()
            naming = " — one of " + ", ".join(f"**{one}**" for one in here) if here else ""
            # The command is named in both branches. An install with no adapter still has to be
            # told what to type, and a refusal that leaves it out is one somebody cannot act on.
            return f"Say which brain: **/provider <name>**{naming}."
        allowed = self._only_one(agent, kind)
        if allowed is None or allowed != who:
            return ("Changing the brain is an agent-wide decision, so it can only be done on a "
                    "channel that one person uses.")
        with locking.only_one(paths.lock(), "this install"):
            try:
                adapters.where(wanted)
            except Exception:                          # noqa: BLE001 — see below
                # **Refused before anything is written**, and named against what this install has.
                known = ", ".join(f"**{one}**" for one in adapters.known()) or "none"
                return f"There is no brain called **{wanted}**. This install has: {known}."
            if wanted_alias:
                try:
                    if not adapters.capabilities(wanted).get("account_aliases", False):
                        return f"**{wanted}** does not support additional account aliases."
                    accounts.account_home(wanted, wanted_alias)
                except accounts.Refused as why:
                    return str(why)
            settled = records.read(directory.records(agent))
            same_provider = (accounts.same(
                str(settled.get("provider_name") or ""), settled.get("provider_alias"),
                wanted, wanted_alias) if wanted_alias else
                str(settled.get("provider_name") or "") == wanted)
            if same_provider and settled.get("provider_alias") == wanted_alias:
                return f"**{agent}** already answers on **{_shown_provider(wanted, wanted_alias)}**."
            records.stated(directory.records(agent), {
                "provider_name": (adapters.canonical(wanted) if wanted_alias else wanted),
                "provider_alias": wanted_alias})
            found = arriving.standing_in(agent, place)
            if found is not None:
                kept.forget_sessions(agent, found)
        shown = _shown_provider(wanted, wanted_alias)
        return f"**{agent}** now uses **{shown}**. This conversation starts fresh."

    def _only_one(self, agent: str, kind: str) -> Optional[str]:
        """The single person this channel allows, or `None` where it allows any other number.

        **A channel that allows a place allows an unknown number of people**, so it is never this
        one however few senders stand beside it: who is in a room is the platform's to change, and
        an agent-wide default is not something a room's membership gets to decide.
        """
        with contextlib.suppress(Exception):
            allowed = channels_kept.admitting(channels_kept.one(agent, kind))
            if len(allowed.senders) == 1 and not allowed.places:
                return allowed.senders[0]
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
        running = turns.forget_when_done(agent, found)
        if running:
            return ("🧹 The next message starts fresh. A turn is still running, and what it says "
                    "will be the last of the old conversation.")
        return "🧹 Started fresh. The next message begins a new session."

    def _stopped(self, agent: str, kind: str, place: str) -> str:
        """End the turn running here, or the work that never reached one (R-CH-9, R-CH-36).

        **A message no turn ever admitted is still work somebody is waiting on.** Admission can be
        refused before a turn exists — an install-wide change holds the admission barrier for a few
        seconds — which leaves the message durably pending, the place showing an indicator with
        nothing behind it, and this answering "nothing is running here" while the person watches
        their agent appear to type for ever.

        So the pending tail is settled through the same path work stopped before its provider began
        already takes, and no brain runs. An older message a later turn has already superseded is
        not settled, marked or replayed, because the rows this may settle are the same ones a
        replacement gateway may recover.

        **Two things keep the word "stopped" true**, and each was a way of saying it and being
        wrong. Nothing this stop leaves behind may still run, which is what taking the tail from its
        newest end guarantees on a conversation holding more rows than one claim may hold. And only
        the ids that were *actually* associated with the stopped turn are marked — a turn published
        in the moment between reading those rows and claiming the conversation is what this stops
        instead, and it marks its own message when it ends.
        """
        found = arriving.standing_in(agent, place)
        if found is None:
            return "✋ Nothing is running here."
        if turns.busy(agent, found):
            if turns.stop(agent, found):
                return "✋ Stopped."
            # Busy, and not by anything this process is running — a scheduled turn takes a process
            # of its own. Said as what it is rather than as a failure, because trying again will
            # not help.
            return "✋ Something is running here, but not something I can stop from a conversation."
        # **From the newest end, so a bounded answer is still a whole one.** Claiming the newest
        # row supersedes every older unclaimed one, which is the same rule a replacement gateway
        # applies — so a conversation holding more unclaimed rows than this leaves none that could
        # still run. Taking the oldest of them would leave the very rows a sweep starts with.
        pending = arriving.pending_on_channels(
            agent, PENDING_STOPPED_AT_MOST, channels=(kind,), conversation=found, newest=True)
        if not pending:
            return "✋ Nothing is running here."
        stopped = turns.stop_or_settle_pending(
            agent, found, tuple(one.landed.message for one in pending))
        if stopped.settled:
            became = set(stopped.settled)
            for one in pending:
                if one.landed.message not in became:
                    continue
                # The terminal state ends the place's indicator as well as marking the message,
                # which is the whole of what the person asked for and is one record rather than two.
                hosting.marked(agent, self._where, self._hosted(), kind, place, STOPPED,
                               one.external_id)
            return "✋ Stopped."
        if stopped.live:
            # A turn was published between reading those rows and claiming the conversation, so
            # what this stopped is that turn and every row read above is still pending. It writes
            # its own outcome and marks its own message; marking this snapshot would put ✋ on work
            # that is still waiting for a turn and would then be answered anyway.
            return "✋ Stopped."
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


def _markdown_text(said: Any) -> str:
    """One literal line inside Markdown, without letting stored punctuation reshape the list."""
    flattened = " ".join(str(said or "").split())
    return "".join(f"\\{one}" if one in "\\`*_~|" else one for one in flattened)


def _granted_skills(agent: str) -> List[str]:
    """Granted names, keeping absent and malformed grant stores as different answers."""
    at = grants.where(agent)
    try:
        mode = at.lstat().st_mode
    except FileNotFoundError:
        return []
    if not stat.S_ISDIR(mode):
        raise OSError(f"{at} is not a grants directory")
    return [one.name for one in grants.held(agent)]


def _what_agents_are() -> str:
    """Every agent, what it is for, and the skills it holds (R-DIS-42).

    An unreadable field is one field, never an unreadable agent. The directory is the authority on
    which agents exist, so a damaged description or grants directory cannot make one disappear from
    an install-wide listing.
    """
    try:
        agents = sorted(directory.known(), key=lambda name: (name.casefold(), name))
    except Exception as why:                           # noqa: BLE001 — an inspection boundary
        return f"I could not read the agents ({type(why).__name__})."
    if not agents:
        return "No agents."

    said = []
    for agent in agents:
        try:
            row = records.read(directory.records(agent))
            provider = _markdown_text(_shown_provider(
                str(row.get("provider_name") or ""), row.get("provider_alias"))) \
                or "provider unknown"
            description = _markdown_text(row.get("describes")) or "no description"
        except Exception:                              # noqa: BLE001 — one damaged agent stays listed
            provider = "provider cannot be read"
            description = "description cannot be read"
        try:
            skills = sorted(_granted_skills(agent),
                            key=lambda name: (name.casefold(), name))
            holding = ", ".join(_markdown_text(one) for one in skills) or "none"
        except Exception:                              # noqa: BLE001 — independent inspection field
            holding = "cannot be read"
        said.extend((f"- **{_markdown_text(agent)}** ({provider}) — {description}",
                     f"  - Skills: {holding}"))
    return "\n".join(said)


def _what_is_coming(agent: str) -> str:
    """The schedules that can still run, soonest first (R-DIS-37).

    **What can still run**, rather than everything ever written down: one whose moment has gone is
    not something anybody is deciding about, and a list carrying them would bury the two that matter
    under a year of history. One nobody could understand is named rather than dropped, because a
    schedule missing from a list reads as a schedule that is not there.
    """
    try:
        # Schedules are stated in the machine's local, zone-less clock. Handing their arithmetic an
        # aware UTC value raises TypeError as soon as it compares the next local minute with `now`.
        now = datetime.datetime.now()
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


def _delegated_prompt(agent: str, conversation: int, delegator: str) -> Tuple[str, Tuple[int, ...]]:
    """The unanswered brief and guidance, oldest first, with their durable message ids.

    Guidance can land before the gateway starts the first turn. Reading only the newest message
    would then replace the brief with that guidance. After an answer, only newer delegator messages
    belong to the resumed turn.
    """
    return turns.delegated_prompt(agent, conversation, delegator)


class OnADelegation(IntoAChannel):
    """Runs the two turns a delegation needs. Handed to `delegations.hosting.looked`.

    **Both directions end in the same three-way answer**, and it is not written here: a turn starts
    when the agent is idle, a word is **said into the turn already running** when it is busy, and it
    is asked again on a short bound when the brain reads nothing mid-turn. That is `_take`, which is
    what a channel message already goes through — so an answer coming back reaches a busy agent the
    same way a person's second message does, rather than waiting for it to be free.

    A thread per turn, daemon, for the reason `OnAChannel.answer` gives: a gateway going down must
    not be held open by one, and what settles a turn is its lock rather than the thread watching it.

    ## Why this reaches a channel at all

    **A turn that answered somebody has to answer them where they are standing.** Waking the agent
    was only ever half of it: the review turn ran, said what it thought of the answer, and wrote that
    into the agent's own records — and there it stopped, because the one thing in this build that
    ever posted to an adapter was the tenant answering a *channel* message. So a person watched their
    agent hand work over, watched nothing come back, and was right. The words existed; the room they
    were owed to was never told.

    It is `IntoAChannel` that both tenants get that from, rather than a second copy of the same
    cutting, attaching and costing — see its docstring. What decides whether anything is sent is the
    conversation, never a flag: one standing on a platform is answered out loud, and one standing on
    nothing is not. **That is also what keeps an answering agent's own room silent** (R-DEL-16) — a
    delegation conversation arrived on no channel, so there is nobody to tell and nothing here has to
    know it is the far side of somebody else's ask.
    """

    def answer_this(self, agent: str, conversation: int, delegation_id: str,
                    delegator: str, provider_name: Optional[str] = None,
                    model_name: Optional[str] = None,
                    provider_alias: Optional[str] = None) -> None:
        """Take the turn that answers another agent. The brief is already the conversation's."""
        threading.Thread(target=self._answered, name=f"delegation-{delegation_id}",
                         args=(agent, conversation, delegation_id, delegator,
                               provider_name, model_name, provider_alias),
                         daemon=True).start()

    def stop_this(self, agent: str, conversation: int, delegation_id: str,
                  delegator: str, provider_name: Optional[str] = None,
                  model_name: Optional[str] = None,
                  provider_alias: Optional[str] = None) -> bool:
        """End delegated work, including a brief stopped before its provider began.

        **Whether anything was reached is the whole of what collection asks**, and it is the same
        question it always asked: a delegation has no platform message to mark, so which of the two
        `turns.Stopped` describes happened changes nothing here.
        """
        _body, messages = _delegated_prompt(agent, conversation, delegator)
        if provider_name is None and provider_alias is None and model_name is None:
            return bool(turns.stop_or_settle_pending(agent, conversation, messages))
        return bool(turns.stop_or_settle_pending(agent, conversation, messages,
                                                 provider_name=provider_name,
                                                 provider_alias=provider_alias,
                                                 model_name=model_name))

    def review_this(self, agent: str, conversation: int, answer: str, from_agent: str,
                    delegation_id: str = "", answer_id: str = "") -> bool:
        """Put an answer in front of the agent that asked for it.

        **Written into that agent's own conversation as `rundesk` first**, so it is history before
        it is a turn: an answer delivered only as a prompt would be one no `rundesk messages` could
        find, and the review turn is not guaranteed to happen at all if the agent is being torn
        down this second.
        """
        said = REVIEW.format(
            agent=from_agent, answer=answer,
            provenance=_delegation_provenance(answer))
        landed = arriving.said_by_rundesk_into(
            agent, conversation, said,
            external_id=f"delegation-result:{delegation_id}:{answer_id}"
            if delegation_id and answer_id else None)
        owning_turn = arriving.turn_for_message(agent, conversation, landed.message)
        if owning_turn is not None:
            # A Words claim happens before its provider write. Only the durable admission record
            # proves that write succeeded; otherwise collection must leave the delegation owed
            # until this worker accepts it or releases it for a fallback turn.
            return turns.admitted_message(agent, owning_turn, landed.message)
        admitted = turns.Admission()
        threading.Thread(target=self._reviewed, name=f"review-{from_agent}",
                         args=(agent, conversation, said, from_agent, landed, admitted),
                         daemon=True).start()
        return admitted.wait(REVIEW_ADMITTED_WITHIN) is True

    def showed(self, agent: str, conversation: int, state: str, to_agent: str,
               delegation_id: str, seconds: Optional[int] = None,
               provider_name: Optional[str] = None,
               provider_alias: Optional[str] = None) -> bool:
        """Say one of `delegations.hosting.SHOWN` where the work was asked for. **Never raises.**

        **The room, found from the conversation** — the same question `_take` asks before it answers
        out loud, and the same answer: a conversation standing on no platform has nobody to tell, so
        this is `False` and nothing else happens. That is what keeps an agent's own room quiet about
        work another agent handed *to* it.

        `provider_name` and `provider_alias` are the delegation's **effective** selection, carried
        straight through rather than looked up: which brain is doing this work was decided once at
        admission, and a second answer read here could disagree with the one the work is running
        under. Absent stays absent — see `channels.hosting.delegating`.
        """
        destination = self._destination(agent, conversation)
        if destination is None:
            return False
        kind, place = destination
        # Rendered here, where `channels.delivery` is reachable and `delegations` is not — the same
        # words the cost line uses for the same quantity, so one turn's `47s elapsed` and one
        # delegation's `47s` are the same measure said the same way.
        elapsed = delivery.duration(seconds) if seconds is not None else ""
        with contextlib.suppress(Exception):
            return hosting.delegating(agent, self._where, self._hosted(), kind, place,
                                      state, to_agent, delegation_id, elapsed,
                                      provider_name or "", provider_alias or "")
        return False

    def _answered(self, agent: str, conversation: int, delegation_id: str,
                  delegator: str, provider_name: Optional[str],
                  model_name: Optional[str],
                  provider_alias: Optional[str]) -> None:
        """One turn answering one delegation. **Never raises** — this is a thread, nobody is above.

        The read is inside the guard and not before it, which is the difference between a claim and
        a fact: an agent removed while its gateway runs makes `arriving.messages` raise, and an
        exception out of a thread target reaches nobody and writes nothing anybody will find.
        """
        try:
            body, message_ids = _delegated_prompt(agent, conversation, delegator)
        except Exception as why:  # noqa: BLE001 — a thread, and nobody is above it
            _note(self._where, f"delegation {delegation_id} could not be read ({why})", logs.ERROR)
            return
        self._take(agent, conversation, body,
                   situation=instructions.AGENT_TO_AGENT, answering=delegation_id,
                   caller_agent=delegator, about=f"delegation {delegation_id}",
                   message_ids=message_ids, provider_name=provider_name,
                   provider_alias=provider_alias,
                   model_name=model_name)

    def _reviewed(self, agent: str, conversation: int, said: str, from_agent: str,
                  landed: arriving.Landed, admitted: turns.Admission) -> None:
        """One turn reviewing what came back. **Never raises.**"""
        stands = arriving.where_it_stands(agent, conversation)
        scheduled = stands is not None and stands[0] == arriving.FROM_SCHEDULE
        schedule = arriving.schedule_name(stands[1]) if scheduled and stands is not None else ""
        schedule_id = None
        if schedule:
            with contextlib.suppress(Exception):
                schedule_id = schedules_kept.one(agent, schedule).get("id")
        self._take(agent, conversation, said,
                   situation=(instructions.SCHEDULE_TO_AGENT if scheduled
                              else instructions.USER_TO_AGENT),
                   answering=None, caller_agent=None,
                   about=f"the answer from {from_agent}",
                   message_ids=(landed.message,), admitted=admitted,
                   schedule_id=schedule_id, schedule_name=schedule)

    def _take(self, agent: str, conversation: int, body: str, situation: str,
              answering: Optional[str], caller_agent: Optional[str], about: str,
              message_ids: Tuple[int, ...] = (),
              admitted: Optional[turns.Admission] = None,
              schedule_id: Optional[int] = None, schedule_name: str = "",
              provider_name: Optional[str] = None,
              provider_alias: Optional[str] = None,
              model_name: Optional[str] = None) -> bool:
        """Start a turn, or say this into the one already running, or ask again in a moment.

        The same three answers `OnAChannel._answered` gives a person's message, and deliberately the
        same: an agent busy on a channel when an answer comes back should read it now rather than
        after whatever it is doing, which is the whole of what steering is for.

        **Only the turn this starts sends anything.** A word said into a turn already running is
        answered by *that* turn, which posts its own final answer with this read into it — so a
        delivery here as well would post the same exchange twice.
        """
        # **Where this conversation actually stands, asked rather than assumed.** `turns` writes the
        # answer back through `said_by_agent`, which finds the conversation from `(source, place)` —
        # so a pair that merely looks right makes a second conversation and an answer nobody reads.
        stands = arriving.where_it_stands(agent, conversation)
        if stands is None:
            _note(self._where, f"{about} names a conversation that is not there", logs.ERROR)
            if admitted is not None:
                admitted.refused()
            return False
        source, place = stands
        # The adapter that speaks to wherever this conversation stands, or `None` where it stands on
        # no platform — a delegation being answered, a schedule, a terminal. Read once here rather
        # than inside the retry, because it cannot change between attempts.
        destination = self._destination(agent, conversation)
        kind, delivery_place = destination if destination is not None else (None, place)
        try:
            for again in range(TRIES):
                try:
                    watching = (_Streaming(self, agent, kind, delivery_place) if kind else None)
                    typing_started = False
                    got = None

                    def started() -> None:
                        nonlocal typing_started
                        # Delegation and review turns have no new platform message to trigger the
                        # ordinary channel path. Admission is the exact moment they become real
                        # work, so a channel-backed conversation must start typing here as well.
                        if kind:
                            typing_started = hosting.marked(
                                agent, self._where, self._hosted(), kind, delivery_place, WORKING)
                        if admitted is not None:
                            admitted.accepted()

                    try:
                        got = turns.run(turns.Request(
                            agent=agent, prompt=body, conversation=conversation,
                            situation=situation,
                            source=source, place=place, answering=answering,
                            schedule_id=schedule_id, schedule_name=schedule_name,
                            caller_agent=caller_agent, inbound_messages=message_ids,
                            provider_name=provider_name, provider_alias=provider_alias,
                            model_name=model_name),
                            # A schedule still owes one final report, not its review activity.
                            watching=(watching.heard
                                      if watching and source == arriving.FROM_CHANNEL else None),
                            admitted=started)
                    finally:
                        if kind and typing_started:
                            became = (AS_A_STATE.get(got.turn_status, FAILED)
                                      if got is not None else FAILED)
                            # No external id: this terminal state ends the place-wide typing
                            # indicator but puts no reaction on a message nobody sent.
                            hosting.marked(
                                agent, self._where, self._hosted(), kind, delivery_place, became)
                    if kind and watching:
                        self._out_loud(
                            agent, kind, delivery_place, got, watching, about,
                            notice=source == arriving.FROM_SCHEDULE)
                    return True
                except turns.Busy:
                    said_into = turns.Admission()
                    if turns.also_say(
                            agent, conversation, body, message_ids, said_into):
                        if said_into.wait() is not True:
                            continue
                        if admitted is not None:
                            admitted.accepted()
                        _note(self._where, f"{about} reached the turn already running")
                        return True
                    if again + 1 < TRIES:
                        time.sleep(BEFORE_ASKING_AGAIN)
            _note(self._where, f"{about} stayed busy, so it was recorded and not answered",
                  logs.ERROR)
            if admitted is not None:
                admitted.refused()
            return False
        except Exception as why:  # noqa: BLE001 — a thread, and nobody is above it
            _note(self._where, f"{about} went wrong ({why})", logs.ERROR)
            if admitted is not None:
                admitted.refused()
            return False

    @staticmethod
    def _destination(agent: str, conversation: int) -> Optional[Tuple[str, str]]:
        """Where this conversation is heard, including a schedule's configured notice DM."""
        stands = arriving.where_it_stands(agent, conversation)
        if stands is None:
            return None
        if stands[0] == arriving.FROM_CHANNEL:
            kind = arriving.on_which_channel(agent, conversation)
            return (kind, stands[1]) if kind else None
        if stands[0] == arriving.FROM_SCHEDULE:
            telling = delivery.notice(agent, "")
            return (telling.kind, telling.place) if telling is not None else None
        return None

    def _out_loud(self, agent: str, kind: str, place: str, got: turns.Outcome,
                  watching: "_Streaming", about: str, notice: bool = False) -> None:
        """Send what the turn settled with to the room it was asked in. **Never raises.**

        Guarded rather than left to the caller's `except`: a platform that would not take the answer
        must not read as the turn having gone wrong, because it did not — the words are in the
        agent's records either way, and what failed is one delivery.

        No mark goes with it. The four marks belong to *a message somebody sent*, and nobody sent
        this one: it is the agent picking its own conversation back up, so there is nothing on the
        platform for a reaction to land on.
        """
        try:
            refused = self._delivered(
                agent, kind, place, got, None, tuple(watching.linked), notice=notice)
        except Exception as why:  # noqa: BLE001 — a thread, and nobody is above it
            _note(self._where, f"{about} could not be sent to {kind} ({why})", logs.ERROR)
            return
        if refused:
            _note(self._where, f"channel {kind}: {about} was not delivered — {refused}", logs.ERROR)


class OnAContinuation(IntoAChannel):
    """Runs a claimed lifecycle recovery directly in its originating conversation.

    It is neither a user message nor a delegation: no inbound conversation row is made and no
    target agent is selected. It resumes the original provider session when safe, otherwise starts
    fresh under current rules. The gateway calls this only after the exact origin channel connects.
    """

    def __init__(self, where: Path, hosted: Callable[[], hosting.Watching]):
        super().__init__(where, hosted)
        self._starting = set()
        self._starting_lock = threading.Lock()

    def resume(self, agent: str, handoff: int) -> None:
        """Start one daemon worker; the durable claim remains the cross-process authority."""
        key = (agent, handoff)
        with self._starting_lock:
            if key in self._starting:
                return
            self._starting.add(key)
        threading.Thread(
            target=self._resumed, name=f"lifecycle-{handoff}", args=(agent, handoff),
            daemon=True).start()

    def _resumed(self, agent: str, handoff: int) -> None:
        key = (agent, handoff)
        try:
            row = continuations.one(agent, handoff)
            stands = arriving.where_it_stands(agent, row.conversation)
            kind = arriving.on_which_channel(agent, row.conversation)
            if stands is None or stands[0] != arriving.FROM_CHANNEL or kind is None:
                continuations.suppressed(
                    agent, handoff, "the originating channel conversation is no longer available")
                return
            _source, place = stands
            watching = _Streaming(self, agent, kind, place)
            typing_started = False
            got = None

            def started() -> None:
                nonlocal typing_started
                # A replacement adapter has no memory of the originating turn's indicator.
                # Admission is the first point at which this continuation is real work, so replay
                # the same state pair every other channel-backed turn owns from that boundary.
                typing_started = hosting.marked(
                    agent, self._where, self._hosted(), kind, place, WORKING)

            try:
                got = turns.run_if(
                    turns.Request(
                        agent=agent, prompt=continuations.prompt(agent, row),
                        conversation=row.conversation,
                        # Recompose the originating person-facing preface. Providers that bind rules
                        # at session creation cannot safely receive a new recovery preface on resume;
                        # turns.run_if requires this composition to match the origin fingerprint.
                        situation=instructions.USER_TO_AGENT,
                        source=arriving.FROM_CHANNEL, place=place,
                        lifecycle_continuation=True, expected_provider=row.provider,
                        expected_provider_alias=row.provider_alias,
                        expected_instructions=row.origin_instructions),
                    admitting=lambda: continuations.claim(agent, handoff) is not None,
                    watching=watching.heard, admitted=started)
            finally:
                if typing_started:
                    became = (AS_A_STATE.get(got.turn_status, FAILED)
                              if got is not None else FAILED)
                    hosting.marked(
                        agent, self._where, self._hosted(), kind, place, became)
            if got is None:
                return
            refused = self._delivered(
                agent, kind, place, got, linked_earlier=tuple(watching.linked))
            outcome = "continuation turn completed"
            if refused:
                outcome += f"; channel delivery was refused ({refused})"
            continuations.delivered(agent, handoff, outcome)
        except turns.Busy:
            # A newer owner turn won admission. Its durable turn/message makes the next claim
            # suppress this handoff; leave it requested for that exact recheck on the next beat.
            return
        except Exception as why:  # noqa: BLE001 — a daemon worker, and nobody is above it
            with contextlib.suppress(Exception):
                continuations.suppressed(
                    agent, handoff, f"the continuation turn could not start ({why})")
            _note(self._where, f"lifecycle continuation {handoff} went wrong ({why})", logs.ERROR)
        finally:
            with self._starting_lock:
                self._starting.discard(key)


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

    A fresh conversation for every invocation, so **a run at three in the morning never lands in
    the exchange somebody is typing into or inherits the prior firing's provider session**. A
    delegated result can still resume this exact invocation for review.
    """
    row = schedules_kept.one(agent, schedule)
    said = due.understood(row)
    if not (said.prompt or "").strip():
        raise Refused(f"{schedule} does not ask {agent} anything — it names a program to start, "
                      f"which is `rundesk schedules run {agent} {schedule}`")
    landed = arriving.recorded_for_a_schedule(agent, schedule, said.prompt)
    return turns.run(turns.Request(
        agent=agent, prompt=said.prompt, conversation=landed.conversation,
        situation=instructions.SCHEDULE_TO_AGENT, schedule_id=row.get("id"),
        schedule_name=schedule, fresh=True, model_name=said.model,
        source=arriving.FROM_SCHEDULE,
        place=arriving.where_it_stands(agent, landed.conversation)[1]))


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


def _shown_provider(provider: str, alias: Optional[str]) -> str:
    """A provider identity safe for a channel, including its optional public alias."""
    shown = _named(provider)
    return f"{shown} ({_metadata_name(alias)})" if alias else shown


def _metadata_name(value: str) -> str:
    """One single-line model or provider value safe to carry in returned evidence."""
    return " ".join(value.replace("\\", "/").rsplit("/", 1)[-1].split())


def _requested_provider_name(value: str) -> str:
    """A requested provider spelling, retaining a relative path without exposing an absolute one."""
    one_line = " ".join(value.replace("\\", "/").split())
    if one_line.startswith("/") or (len(one_line) > 2 and one_line[1:3] == ":/"):
        return one_line.rsplit("/", 1)[-1]
    return one_line


def _note(where: Path, said: str, level: str = logs.INFO) -> None:
    """One line in the gateway's own log, and never a reason to end anything."""
    with contextlib.suppress(Exception):
        if where.parent.is_dir():
            logs.note(where, said, level)
