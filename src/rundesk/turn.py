"""One turn: what it resolved, what it ran, and the account it left behind.

The only module that knows the others exist. `provider` is the seam, `transcript` is the
account and the store is where a conversation got to — each of them is about one thing and
none of them knows about the rest, which is what lets every one be tested on its own. This
is where they meet, and the whole of what it does is:

    resolve -> write down what was resolved -> run the brain -> write down what it said
            -> keep where the conversation got to -> write down how it ended

**What a turn resolves is written when it is admitted and never changed after
(R-RUN-3).** A binding is not a thing anybody maintains here: it is whatever this turn was
asked for, plus what the agent supplies for what was left out, settled once and recorded.

**Nothing is sent that the account does not show (R-RUN-9, R-PRV-10).** Everything that
reaches a brain — the prompt, and anything rundesk ever adds to it — is a record in the
run before the brain is started. Injecting text a person never wrote and leaving it out of
the audit makes the audit a lie, and it is invisible precisely because it *is* the audit.

**A turn takes as long as it takes.** What bounds it is silence, never duration: an agent
that thinks for an hour is working, and a clock that ends it is a clock that ends real
work (R-PROC-6). Nothing here imposes anything shorter than the platform's own window.

**What a turn resolved and what became of it are the run's own columns**, written when it
is admitted and when it ends — not records in a list somebody has to find them in. Two
things rundesk puts into a turn *are* said, and are written as things said: what was asked,
and any standing instructions the surface gave. One is a record of its own, `lost`, which is
where a hole in what the brain reported is written down, in the order it happened.

A brain's six are the only kinds the seam understands, so an adapter that emitted `lost`
would have it kept as a record nobody here knows, exactly like any other.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass, field
from pathlib import Path

from rundesk import activity
from rundesk import agent as agents
from rundesk import process, provider, store, transcript

#: What a conversation is called when nobody named one. A second `rundesk ask` carries the
#: first one on, which is what a person at a terminal means by asking again.
TERMINAL = "terminal"

#: What a conversation the clock started is called, and the surface it happened on. One per
#: schedule, so a scheduled turn is never in the terminal's conversation — which is what it
#: was until this existed: a run at three in the morning resumed the session its owner types
#: into, and left its own prompt and answer in the middle of it.
SCHEDULE = "schedule"

#: A private conversation surface for release-requested backend turns. Their run source is
#: still `schedule`, but their conversation can never be an owner's schedule conversation.
UPDATE = "update"

#: The third, and the one this file does not otherwise name. Written out beside the other two
#: because `began` refuses a word that is not one of `store.SOURCES`, and three spellings of
#: that set — here, there, and in whatever a caller passes — is two too many.
CHANNEL = "channel"

#: How many lines of what a brain said went wrong are carried back with the outcome. The
#: whole of it is in the run's own file; this is the tail worth putting in front of a person.
TROUBLE_KEPT = 20

#: The two rundesk puts into a turn itself, and the one it records about a turn going wrong.
#: `SENT` is a thing *said* and becomes a message; `LOST` is a record, and is the only one of
#: rundesk's own that `store.RECORD_KINDS` knows. Anything else rundesk writes is stored as
#: `unknown` with its own words beside it — which is deliberate for `recovery` and `RETRY`
#: below, both lifecycle bookkeeping about an execution rather than a new shape of owner data,
#: and is a mistake for anything that is neither.
SENT = "sent"
LOST = "lost"

#: What a turn that produced nothing is told to say for itself. Prose rather than one of the
#: closed words, because no brain classified this — rundesk noticed it, and a word from that
#: set would claim an adapter reported something it did not (R-RUN-19).
NOTHING_SAID = "the turn ended without an answer"

#: What is written into the account when a resumed session was handed the turn and gave it
#: straight back. A record of rundesk's own, kept exactly as `recovery` beside it is: this is
#: lifecycle bookkeeping about an execution and not a new shape of owner data, so it is stored
#: as a record nobody's schema knows rather than as a column (R-RUN-24).
RETRY = "retry"
NEVER_RAN = "the resumed session ended without running the turn"


@dataclass(frozen=True)
class Said:
    """A word said into a running turn, and who said it where a surface knows.

    **Identity travels with the word, and no further.** What a person said mid-turn is a
    message of its own and is written down as one — so it needs the same identity the
    message that started the turn already carries, or the same person appears in their own
    history twice, once as a name and once as `user` (R-STO-27). It goes no nearer the
    brain than this: the adapter is handed the words, never who said them.

    A bare string is still accepted by everything that takes these, and means a word nobody
    is named for — which is the terminal, where the only speaker is whoever is at it.
    """

    text: str
    who: str | None = None

    @classmethod
    def of(cls, word) -> "Said":
        return word if isinstance(word, cls) else cls(str(word), None)


@dataclass(frozen=True)
class Outcome:
    """What became of one turn, once it is over."""

    run: str
    ok: bool
    reason: str
    #: What the brain said, in the order it said it — the records we understood.
    said: list = field(default_factory=list)
    #: What it cost, or that nobody said. Never a cost of nothing (R-USE-6, R-USE-7).
    tokens: dict = field(default_factory=lambda: {"reported": False})
    #: Where the conversation got to, when the brain reported one and could carry on.
    handle: str | None = None
    #: Why it failed, in the brain's own words — and the tail of what it said went wrong.
    #: Carried on the outcome rather than left in a file, because a turn that failed with
    #: its one actionable line filed where nobody looks is a turn somebody is stuck on.
    why: str | None = None
    #: The closed word for the same failure, where the brain classified it (R-RUN-19). Never
    #: a replacement for `why`, which keeps saying what the brain actually said: prose is
    #: what a person reads and the word is what anything else can count or branch on. Absent
    #: whenever an adapter did not say, and never inferred from the prose beside it.
    because: str | None = None
    trouble: list = field(default_factory=list)

    @property
    def files(self) -> list:
        """Everything the brain said it made, in the order it said so (R-PRV-20).

        Named by the brain and never guessed at: what a tool printed is not a promise
        that a file exists, and treating it as one would send whatever a brain mentioned.
        """
        return [one for one in self.said if one.get("type") == "file"]

    @property
    def text(self) -> str:
        """What a person asked for, joined back together."""
        return "".join(one.get("text", "") for one in self.said
                       if one.get("type") == "text")

    @property
    def became(self) -> str:
        """What this turn came to, in one word — the word the run's own record holds.

        **Not `reason`, which is what became of the program.** A brain that ran perfectly and
        said it could not answer is a process that finished and a turn that failed, and
        anything reporting the first would say a night's work went fine. One property rather
        than the expression written wherever it is needed, because the two would drift and the
        drift would be silent: a schedule saying `finished` about a turn that did not.
        """
        return "finished" if self.ok else ("failed" if self.reason == process.FINISHED
                                          else self.reason)


class CannotResume(RuntimeError):
    """An interrupted turn has no provider session that can safely be continued."""


async def carry(
    name: str,
    prompt: str,
    named: str,
    where: Path | None = None,
    model: str | None = None,
    settings: dict | None = None,
    posture: str = provider.WORK,
    conversation: str = TERMINAL,
    on: str = TERMINAL,
    kind: str = TERMINAL,
    fresh: bool = False,
    watching=None,
    steering=None,
    root: Path | None = None,
    now=None,
    pick=None,
    asked_by: dict | None = None,
    admitted=None,
    preface: str = "",
    source: str | None = None,
    schedule_id: int | None = None,
    resume_required: bool = False,
    prompt_author: str = "user",
    resume_on_interrupt=None,
    stopped_by_owner=None,
    recovery_of: str | None = None,
    started=None,
) -> Outcome:
    """Run one turn for this agent, and write down everything about it.

    `named` is the brain as the owner named it — a shipped adapter or a path to a program
    — and it is carried through rather than looked up in any list. `watching` is handed
    each record as it arrives, for a terminal that is showing the turn as it happens; the
    account is written whether or not anyone is watching.

    `asked_by` is whatever the thing that admitted this turn wants the account to show
    about where it came from — a channel and the person who spoke, when one did. Carried
    into the admitted record and never read here, so the turn goes on knowing nothing
    about surfaces (R-CH-15).

    **A conversation is a place, not a string.** `conversation` is what the surface calls
    the space this is happening in — a Discord channel id, or `terminal` — and `on` and
    `kind` are which surface that is. The three together are what makes one conversation
    one conversation, so two turns arriving in the same room weeks apart carry on from
    each other and two rooms that happen to share an id do not.

    `preface` is what the thing that admitted this turn wants the brain told about the
    situation before it reads a word of the prompt — an owner's standing instructions for
    this surface, or for this schedule. Handed to the adapter as its own thing rather than
    folded into the prompt, so a brain that has somewhere to put standing instructions can
    put them there. Written into the account, because a turn that read something the
    person never typed has to be readable afterwards as having read it.

    `admitted` is told the run's id and what the brain can do, the moment there is a run
    and before the brain is started. Anything showing a turn as it happens needs both:
    the id to name the run from its first mark, since waiting for the outcome to learn it
    leaves everything shown while somebody is waiting uncorrelated — and the capabilities
    to know what to offer, since offering to interrupt a brain that cannot be steered
    offers something that cannot happen (R-PRV-15).
    """
    at = provider.program(named)          # raises NotRunnable, before anything is written
    whose = agents.paths(name, where)
    brain = provider.key(named)
    # **Named, never made.** An adapter is told where a home of its own *would* be and is
    # free to use it for its own small bookkeeping — but rundesk does not create it, and no
    # brain is pointed at it. Pointed at one, a real brain does not merely keep a sign-in
    # there: it builds its whole state tree, to tens of megabytes an agent, and starts out
    # signed out so every agent needs its own login. An adapter's job is to reach the brain
    # the machine already has.
    home = agents.provider_home(name, brain, where)
    # Made before the brain is started, because the path to what it prints is handed to
    # a program: an adapter told to append to a file in a directory nobody made is one
    # that fails for a reason that has nothing to do with the brain.
    transcript.home(whose["logs"]).mkdir(parents=True, exist_ok=True)
    # Swept here rather than on a schedule of its own, for the reason `backups add` prunes
    # where it does: this is the moment a new one arrives, so it is the moment the question
    # has a new answer, and an agent nothing runs stops accumulating anything to sweep
    # (R-RUN-23). The gateway would be the wrong place — it knows nothing of agents, and
    # these belong to one.
    transcript.sweep(whose["logs"])

    can = await provider.capabilities(at, provider.environment(
        home=whose["run"], cwd=whose["home"], provider_home=home, skills=whose["skills"],
        run="capabilities", posture=posture, path=None,
    ))
    kept = agents.records(name, where)
    where_it_is = kept.opened(store.conversation_id(on, conversation), on, kind,
                              conversation, store.stamped(now))["id"]
    resume = None
    if can["resume"] and not fresh:
        resume = kept.session(where_it_is, brain)
    if resume_required and not resume:
        raise CannotResume(
            "the interrupted turn could not be resumed because no provider session was saved"
        )

    at_now = store.stamped(now)
    if preface:
        # Written down as something *rundesk* said into the conversation, because a turn
        # that read standing instructions read something the person never typed — and an
        # account that does not show it cannot explain afterwards why it answered as it
        # did (R-RUN-9). `rundesk` is an author for exactly this.
        kept.arrived(where_it_is, at_now, preface, author="rundesk")
    # What was asked, written *before* the run that answers it — so the run says what
    # caused it (R-STO-10) rather than being linked to it afterwards, and so a turn that
    # died before it reached the brain still shows what somebody asked for.
    who = (asked_by or {}).get("user") or None
    if prompt_author != "user":
        who = None
    asked = kept.arrived(
        where_it_is, at_now, prompt, author=prompt_author, who=who,
    )
    run = kept.began(
        # How this turn came about, and one of the three the records declare (R-RUN-16).
        # Said by the caller where the caller knows something this cannot work out — the
        # clock does — and derived otherwise from whether a surface asked.
        source or (CHANNEL if asked_by else TERMINAL), named, posture, at_now,
        conversation_id=where_it_is, schedule_id=schedule_id,
        trigger_message_id=asked, model=model, can=can,
        settings=settings, resumed=bool(resume), pick=pick,
    )
    if admitted is not None:
        admitted(run, dict(can))
    # **A run that was begun is settled, whatever happens next** (R-RUN-13). Everything
    # below can be cancelled — a gateway standing down mid-turn is the ordinary way — and a
    # cancellation is not an exception the body can catch on its way past: it unwinds
    # straight through `ended` below, leaving the run marked `running` in an owner's records
    # for ever. `rundesk runs` then shows a turn still going that nothing is doing, and no
    # restart clears it because nothing afterwards knows it was ever begun.
    #
    # A list rather than a flag because the settling happens inside the `with` and the
    # guard below reads it on the way out: what is remembered is *that* it was settled, and
    # what it was settled as is worth having for anyone debugging one of these.
    #
    # Entered outside `_Account`, so it is the last thing to unwind and the account is
    # already closed when it writes.
    settled: list = []
    with _settled_whatever_happens(
            kept, run, settled, now, recoverable=resume_on_interrupt,
            by_owner=stopped_by_owner), \
            _Account(kept, run, where_it_is, transcript.beside(whose["logs"], run),
                     now=now) as writing:
        if recovery_of:
            # The old run names this one when it is admitted; this is the other direction.
            # Appended before the provider starts, so another interruption still leaves a
            # truthful audit trail linking both executions (R-RUN-17).
            writing.add(event={"type": "recovery", "run": recovery_of})
        # What the brain said, and what it said went wrong — the turn's, not one attempt's.
        # Kept as well as written down, so what went wrong can be shown to whoever asked.
        said: list = []
        trouble: list = []
        source_name = source or (CHANNEL if asked_by else TERMINAL)

        def provider_started(pid: int) -> None:
            activity.began(whose["run"], {
                "run": run,
                "source": source_name,
                "surface": on,
                "conversation": conversation,
                "pid": pid,
                "since": time.time(),
            })
            if started is not None:
                started(pid)

        async def attempt(carrying: str | None, steer_with) -> process.Result:
            """Start the brain once for this turn, and write down what it says.

            One turn may start a brain twice — see below — and everything a start needs
            lives here so the second one is the same start rather than a copy of it that
            drifts. `said`, `trouble` and the account are the turn's and are added to by
            each attempt, because they are the account of the *turn*.
            """
            program = process.Program(
                [str(at)],
                env=provider.environment(
                    home=whose["run"], cwd=whose["home"], provider_home=home,
                    skills=whose["skills"], run=run,
                    model=model, resume=carrying, posture=posture, settings=settings,
                    raw=transcript.printed(whose["logs"], run), preface=preface,
                ),
                # **The agent's home, not its workspace.** A brain loads the rules it is to
                # follow because they *stand in the directory it stands in* — that is the
                # whole mechanism, and it is what the scaffolded `AGENTS.md` says out loud.
                # Standing it one directory lower put every one of those files out of its
                # reach: the agent was asked who it was and answered, truthfully, that
                # there was nothing here to tell it. `workspace/` is still where it works,
                # by instruction, which is what that file also says.
                cwd=whose["home"],
                takes_input=True,
                errors_apart=True,
                on_error=_noting(writing, trouble),
            )
            # Written before the brain is started, because what is sent is what the account
            # has to show — and an account written afterwards is one that can be written to
            # match whatever happened. A steered turn records it as it sends it instead, so
            # that everything said mid-turn lands in the order it was said.
            #
            # **One gate, asked once.** This used to be decided by what the brain can do
            # and again inside `_run` by whether the caller had anything to steer with. The
            # two look interchangeable right up until the caller has nothing to add — which
            # is every ordinary `rundesk ask` — and then the record was skipped here and
            # never written there, so a turn reached a brain with nothing in its account to
            # show for it (R-RUN-9, R-PRV-10).
            if not can["steer"]:
                writing.add(event={"type": SENT, "text": prompt})
            try:
                return await _run(
                    program, prompt, writing, said, watching,
                    steer=can["steer"], steering=steer_with, started=provider_started,
                )
            finally:
                activity.ended(whose["run"], run)
                # The adapter has finished with the file by now, so this is the one moment
                # the ceiling can be applied to a stream rundesk itself never writes. In the
                # `finally`, because a turn that was interrupted printed just as much as one
                # that was not (R-RUN-22).
                transcript.trim(whose["logs"], run)

        result = await attempt(resume, steering)
        # **Only a prompt that stands on its own is worth asking again.** Everything rundesk
        # writes into a turn itself is a *continuation* — "carry on where the last gateway
        # stopped", "finish what you were doing before the update" — and those mean nothing
        # at all without the session they were written for. Asked on a fresh one, the brain
        # answers about nothing, the turn is recorded as finished, and the handle the retry
        # ends on replaces the interrupted conversation's own, which is the work itself
        # going (R-GW-22). A recovery turn is refused outright rather than resumed
        # elsewhere, and this is the same refusal one attempt later.
        if prompt_author == "user" and _never_ran(said, result, resumed=bool(resume)):
            # **The question is still worth asking, so it is asked** (R-RUN-24). A resumed
            # session that hands the turn straight back never read the prompt, and rundesk
            # is the only layer that knows both that nothing was said and what the person
            # originally wanted. Discarding it consumed two real questions on a live
            # gateway inside 82 minutes, each answered with an activity mark and silence.
            #
            # Once, and on a fresh session — the stale session is the fault, so carrying it
            # again would buy the same silence twice. Written into the account first, so a
            # turn that started a brain twice is never a turn that looks like it started one.
            writing.add(event={"type": RETRY, "why": NEVER_RAN})
            # Nothing to steer with the second time. Whatever a person said into the first
            # attempt is already in the account and already consumed; re-reading an iterator
            # that is spent is not a second chance at it, and the prompt — which is what was
            # lost — is sent again in full.
            result = await attempt(None, None)

        # Inside the same writer, and last. A second one would count from nothing and
        # give the end of a run the same places in the order as its beginning.
        handle = _handle(said)
        carried = bool(handle) and can["resume"]
        if carried:
            kept.remember_session(where_it_is, brain, handle)
        tokens = _tokens(said)
        ended = _ended(said)
        # A turn that said nothing is not a turn that worked. Measured: a resumed session
        # reported `done ok:true` with a usage record of four zeros one second after it
        # started, and said nothing else at all. The run was written down as `finished`
        # and the message that asked for it was marked answered — so the person who asked
        # was told their question had been dealt with, the question was consumed, and
        # nothing had happened to it. A program exiting well is not an answer, and this is
        # the only place that can tell the two apart before a surface acts on it.
        answered = _answered(said)
        ok = result.ok and ended is not False and answered
        why = _why(said) or (None if answered else NOTHING_SAID)
        # What the brain finally said, as one thing said in the conversation. Written at
        # the end because it is only whole then: a reply arrives a fragment at a time, and
        # a row per fragment is a history nobody can read back and a search that matches
        # half a sentence.
        #
        # **A turn the clock started answers with its close, and no other kind does**
        # (R-SCH-45). A turn somebody is watching shows its working as it goes and its last
        # thought is already the answer, because the surface sends each earlier one on as it
        # is finished. A scheduled turn never passes that way: it runs headless, and what it
        # said is read back out of this one row afterwards — so everything it thought aloud
        # on the way arrived as a report with the report buried at the end of it.
        writing.answered(_close(said) if source_name == SCHEDULE else _reply(said))
        # Built here rather than at the end, so the word written down and the word handed
        # back are the same word: `Outcome.became` is the one place it is worked out, and a
        # second copy of that expression would drift into a run recorded as finished and a
        # schedule reporting it as failed, or the other way round.
        outcome = Outcome(run=run, ok=ok, reason=result.reason, said=said, tokens=tokens,
                          handle=handle if carried else None, why=why,
                          because=_because(said),
                          trouble=[one for one in trouble if one.strip()][-TROUBLE_KEPT:])
        # How it finished, in one word. A turn is `finished` only when the program ended
        # well *and* the brain did not say otherwise — a brain that answered "no" through
        # a process that exited zero is a failed turn, and the two used to be told apart
        # by two fields that a reader had to combine correctly to get right.
        kept.ended(run, store.stamped(now), outcome.became, exit_code=result.code,
                   why=why, tokens=tokens, because=outcome.because)
        settled.append(outcome.became)
    return outcome


#: What a run that never got to say for itself is recorded as. `stopped` rather than
#: `failed`, because "it stopped" and "it broke" are different news about the same silence
#: — the same distinction `channel.STATES` already draws — and a gateway standing down
#: mid-turn is the ordinary way this happens rather than a fault.
INTERRUPTED = "stopped"
INTERRUPTED_WHY = "the gateway stopped while this turn was running"
#: The same silence, for the opposite reason. A person's `/stop` cancels a turn exactly as a
#: shutdown does, so nothing downstream could tell the two apart afterwards and every stop
#: was written down as a gateway outage — which makes "did my gateway fall over last night?"
#: unanswerable from the records, the one question the field exists for (R-RUN-13).
STOPPED_WHY = "a person stopped this turn"


@contextlib.contextmanager
def _settled_whatever_happens(kept, run: str, settled: list, now, recoverable=None,
                              by_owner=None):
    """Leave no run marked as still going once nothing is doing it (R-RUN-13).

    **The path this exists for cannot be caught by the body it wraps.** A gateway standing
    down cancels the turn, and a cancellation unwinds straight past the `ended` at the end
    of the happy path — so a run that had been admitted stayed `running` in an owner's own
    records for ever. `rundesk runs` went on showing a turn in flight that nothing was
    doing, no restart cleared it because nothing afterwards knew it had been begun, and a
    later turn on the same agent succeeded beside it, which is what makes it look like two
    gateways rather than one bad record.

    **Exactly once**, which is the other half: the happy path has already written the real
    outcome and this must not write a second one over it. `settled` is how the two agree.

    Written even while the process is being taken down, so it is kept as narrow as it can
    be — one row, no reading, and anything that goes wrong swallowed. A settlement that
    raised on the way out of a cancelled turn would replace one bad record with a worse
    traceback, and the thing it is protecting is a database write nobody is waiting on.
    """
    try:
        yield
    finally:
        if not settled:
            with contextlib.suppress(Exception):
                kept.interrupted(
                    run, store.stamped(now),
                    STOPPED_WHY if by_owner is not None and by_owner() else INTERRUPTED_WHY,
                    recoverable=bool(recoverable is not None and recoverable()),
                )
                settled.append(INTERRUPTED)


class _Account:
    """What one run did, written down as it does it.

    Rundesk's own records and a brain's went into one file and are told apart here
    instead. **What was said is a message and what happened is a record**, because the two
    are read for different things: a person reads a conversation back and searches it by
    the words in it, and an owner reads a run back to find out what it did.

    `seq` is a total order that does not depend on a clock (R-RUN-7), so an account still
    reads in the order the work happened on a machine whose clock went backwards.

    What the brain itself printed is not here. It goes to a file beside the log, because
    the path is handed to a program that may be a shell script — and that file may be
    destroyed, so nothing a run recorded is recoverable only from it (R-STO-5).
    """

    #: Every kind of record a brain may report, mapped to how it is kept. `text` is what it
    #: *says*, which is a message; the rest are what it *did*. Anything else it reports is
    #: kept as `unknown` with its own words beside it, because a record nobody could read
    #: today is still there to be read later (R-RUN-6).
    SAID = "text"

    def __init__(self, kept, run: str, conversation: str, errors, now=None):
        self.run = run
        self._kept = kept
        self._conversation = conversation
        self._errors = errors
        self._now = now or time.time
        self._seq = 0
        self._wrote = None

    def __enter__(self):
        return self

    def __exit__(self, *gone):
        if self._wrote is not None:
            self._wrote.close()
            self._wrote = None
        return False

    def add(self, event: dict | None = None, raw: bytes | None = None) -> int:
        """One thing that happened, added and never rewritten (R-RUN-5).

        What was *said* is not a record: it is a message, in the conversation it was said
        in, and writing it both ways would make the answer two things that could disagree.
        Only what happened claims a place in the order, so the order has no holes in it
        where something that was not a record went by.
        """
        at = store.stamped(self._now)
        kind = (event or {}).get("type")
        if kind == SENT:
            # The prompt is already a message: it was written before the run, because a
            # run has to say what caused it. What reaches here without `mid` *is* that
            # one. What reaches here with it is a word somebody said while the turn was
            # already running, which is a message of its own and belongs in the order it
            # was said (R-RUN-9).
            if event.get("mid"):
                # Named the same way the prompt was. Without this the same person was
                # recorded twice over in one conversation — by their platform identity
                # when they started a turn, and as the bare word `user` whenever they
                # spoke into one already running (R-STO-27).
                author = event.get("author")
                self._kept.arrived(
                    self._conversation, at, str(event.get("text") or ""),
                    author=author or "user",
                    who=None if author else (event.get("who") or None),
                )
            return self._seq
        if kind == self.SAID:
            # Gathered, not recorded. A reply arrives a fragment at a time and is one
            # thing said; it is written whole when the turn ends.
            return self._seq
        self._seq += 1
        self._kept.recorded(
            self.run, self._seq, at,
            kind if kind in store.RECORD_KINDS else "unknown",
            event=event,
            raw=raw.decode("utf-8", "replace") if raw is not None else None,
        )
        return self._seq

    def answered(self, text: str) -> None:
        """What the brain finally said. Nothing is written for a turn that said nothing."""
        if text.strip():
            self._kept.answered(self._conversation, self.run, store.stamped(self._now), text)

    def went_wrong(self, said) -> None:
        """One line of what the brain said went wrong, kept and kept apart (R-PRV-6).

        A file rather than a row, and beside what it printed: this is an operating-system
        pipe, and it may be destroyed to reclaim space without the account losing anything.
        """
        if self._wrote is None:
            self._errors.parent.mkdir(parents=True, exist_ok=True)
            self._wrote = open(self._errors, "ab")
        line = said if isinstance(said, bytes) else str(said).encode("utf-8", "replace")
        self._wrote.write(line if line.endswith(b"\n") else line + b"\n")
        self._wrote.flush()


def _noting(writing, trouble: list):
    """Write down what the brain said went wrong, and keep it to hand as well.

    Written down because it is part of the account of the run; kept because a person who
    just watched a turn fail should not have to know which file to open to find out why.
    """
    def noted(line: str) -> None:
        trouble.append(line)
        writing.went_wrong(line)
    return noted


async def _run(program, prompt: str, writing, said: list, watching,
               steer: bool = False, steering=None, started=None) -> process.Result:
    """Start the brain, feed it the turn, and write down every line it answers with.

    The sink is the account itself. Every line lands in the run's raw exactly as it
    arrived and, when it is one of the six the seam understands, in the account as well —
    so a record of a kind nobody here knows keeps its place in the order and is still
    there to be read afterwards (R-PRV-5).
    """
    def heard(one) -> None:
        if isinstance(one, process.Gap):
            # Where the loss happened, in the account, rather than as a number at the
            # end: records are not independent, and a hole nobody is told about is not
            # less of an answer but a wrong one.
            writing.add(event={"type": LOST, "records": one.records, "why": one.why})
            return
        understood = provider.understood(one)
        writing.add(event=understood, raw=one)
        if understood is not None:
            said.append(understood)
            if watching is not None:
                watching(understood)

    await program.start()
    try:
        if started is not None:
            started(program.pid)
    except BaseException:
        # Registration happens after spawn because it needs the PID. If that boundary
        # fails, do not leave a provider running with nobody reading or owning it.
        await program.end()
        raise
    reading = asyncio.ensure_future(program.wait(sink=heard))
    if not steer:
        # Decided by what the brain said it can do, and by nothing else. A brain that
        # cannot be sent to mid-turn is given the prompt and told there is no more coming,
        # so one that reads its input to the end can answer at all — and one that *can* is
        # given records whether or not anybody has a second thing to say, because that is
        # what it was promised and what it is written to read.
        try:
            await program.send(prompt.encode("utf-8"))
            await program.close_input()
        except process.NotListening:
            pass  # it answered and left before we finished writing; not a failure
        return await reading
    # A brain that can be steered has its input held open and gets records rather than
    # plain text, because nothing can mean "the prompt ended" any more. Everything sent is
    # written into the account first: a word put into a turn that the account does not
    # show makes the account a lie, and this is the one thing that adds words mid-turn.
    # What went wrong saying it, if anything did. Read after the turn rather than raised
    # through it: the brain may well have finished properly, and a word that never reached
    # it is a hole in the account rather than a reason to throw the account away.
    trouble: list = []
    saying = asyncio.ensure_future(
        _saying(program, prompt, writing,
                steering if steering is not None else _nothing(), trouble))
    try:
        result = await reading
    finally:
        saying.cancel()
        with contextlib.suppress(BaseException):
            await saying
    if trouble:
        # Counted the same way a record the receiver never got is counted, because it is
        # the same kind of loss seen from the other end: something belonging to this turn
        # did not make it. A turn that lost a word must not report that it was fine.
        return process.Result(result.reason, result.code, result.output,
                              result.undelivered + len(trouble))
    return result


async def _nothing():
    """Nothing more to say, said in the one shape the sender reads.

    A turn with no second word still goes down the steered path, because the path is the
    brain's to choose and not the caller's — so the absence of anything to add has to be
    expressible rather than a reason to take the other one.
    """
    return
    yield  # noqa: unreachable — what makes this an async iterator rather than a coroutine


async def _saying(program, prompt: str, writing, steering, trouble: list) -> None:
    """The prompt, and anything said after it while the brain is still working.

    **Nothing that goes wrong in here is allowed to be silent.** This runs as a task of its
    own, and a task whose exception nobody retrieves is one that failed invisibly — so a
    word that could not be written down, or a terminal that raised while somebody was
    typing into it, would leave the turn reporting that it was fine. What went wrong is put
    into the run's account and into `trouble`, which the turn's outcome reads.

    A brain that has already finished is the one exception: somebody still typing at a turn
    that is over is nobody's fault, and there is nothing lost to report.
    """
    try:
        writing.add(event={"type": SENT, "text": prompt})
        await program.send(provider.spoken(prompt))
        async for word in steering:
            said = Said.of(word)
            writing.add(event={"type": SENT, "text": said.text, "mid": True,
                               "who": said.who})
            writing.add(event={"type": SENT, "text": provider.STEERING_CONTEXT, "mid": True,
                               "author": "rundesk"})
            await program.send(provider.spoken(
                said.text, context=provider.STEERING_CONTEXT))
    except process.NotListening:
        pass  # it finished while somebody was still typing, which is nobody's fault
    except asyncio.CancelledError:
        raise  # the turn ended first and this is being tidied up; not a loss
    except BaseException as why:
        trouble.append(str(why) or why.__class__.__name__)
        with contextlib.suppress(BaseException):
            writing.add(event={"type": LOST, "records": 1, "why": f"not said: {why}"})
    # **Whatever happened, the brain is told there is no more coming.** A steerable brain
    # reads until its input closes; leaving it open because *we* went wrong is a turn that
    # never ends, waiting on somebody who has already stopped speaking.
    with contextlib.suppress(BaseException):
        await program.close_input()


#: Going to work, in the brain's own records. An adapter reports the call and it reports the
#: call's one terminal update; both are here because a tool already over by the time this
#: process heard of it arrives as a `result` alone, and the seam must still be found.
WENT_TO_WORK = ("tool", "result")


def _thoughts(said: list) -> list:
    """What the brain said, split where it finished a thought.

    **A finished thought ends a paragraph; a fragment does not.** Every `text` record used
    to be concatenated with nothing between it and the next, which is right for fragments
    and wrong for whole thoughts — a brain that says several complete things as it works
    had the last word of one run into the first word of the next, so an account read back
    `caught it running.The worker`. The seam already carries the distinction, because an
    adapter marks a finished thought `whole` for exactly this; nothing here read it.

    Fragments are still joined with nothing, because a reply arriving a piece at a time is
    one sentence and not several.

    **A brain that never marks anything finished still finishes a thought by going to
    work.** `whole` alone is not a seam every adapter has: of the four that ship, `grok`
    refuses it on purpose — it writes its reply a token at a time and nothing in the stream
    ever restates it — and `antigravity` streams its response as deltas, marking `whole`
    only on a terminal fallback taken when nothing streamed at all. Read on `whole` alone,
    every turn either of them takes is one thought, so `caught it running.The worker` comes
    straight back for them and a scheduled turn's close is everything it said. What both do
    report is the moment the brain stopped talking and called a tool, and that is the same
    seam said another way: a thought said *before* further tool calls is working narration.
    So the split is defined for every adapter that ships, and a brain that streamed straight
    through without ever going to work said one thing — which is both its reply and its
    close, and is right, because there was no working to drop.

    One split, read two ways: everything as one reply, and the last of them on its own. Two
    walks of the same records would agree until one of them was changed, and then a turn
    would deliver a thought that is not the one its account says it ended on.
    """
    parts, piece = [], ""
    for one in said:
        kind = one.get("type")
        if kind in WENT_TO_WORK:
            # Whatever was open is finished: the brain left off saying it to do something.
            if piece:
                parts.append(piece)
                piece = ""
            continue
        if kind != "text":
            continue
        text = str(one.get("text") or "")
        if not one.get("whole"):
            piece += text
            continue
        # A whole thought closes whatever fragments were still open, then stands alone.
        if piece:
            parts.append(piece)
            piece = ""
        parts.append(text)
    if piece:
        parts.append(piece)
    # Stripped of the blank lines a brain put at its own edges, never of the ones inside a
    # thought: what is between paragraphs here is rundesk's, and what is within one is the
    # brain's and is left exactly as it said it.
    return [kept for kept in (part.strip("\n") for part in parts) if kept.strip()]


def _reply(said: list) -> str:
    """Everything the brain said, as the one thing it said (R-PRV-22)."""
    return "\n\n".join(_thoughts(said))


def _close(said: list) -> str:
    """The last whole thing the brain said — what a turn the clock started answers with
    (R-SCH-45).

    **Decided after the turn is over, which is the only moment it is a fact.** A brain
    cannot mark its own final message: it says something, then decides whether to call
    another tool, and only if it does not does that thought turn out to have been the last.
    Asked here, once there is no more coming, "which was last" is read rather than guessed.

    A multi-paragraph answer survives whole, because one finished thought is one record and
    the blank lines inside it are the brain's. What is dropped is a thought said *before*
    further tool calls, which is working narration and is what this exists to drop.

    **On every adapter, including the two that never mark a thought finished.** `_thoughts`
    ends an open run of fragments where the brain went to work, so `grok` and `antigravity`
    close on their last uninterrupted run rather than on the whole turn. What that costs is
    stated there: a brain of theirs that narrates and answers in one breath, with no tool
    call between, delivers both — there is no seam in what it said, and inventing one would
    cut a sentence in half.

    The turn is not lost with it: every record the brain reported is in the run's own
    transcript, exactly as it arrived (R-PRV-5). It is not in the run's account, which keeps
    what a turn *did* and never what it said — and that transcript is bounded to its own
    tail on every turn (R-RUN-22) and may be destroyed entirely to reclaim space (R-STO-5,
    R-RUN-23). The trim is the near one: it keeps the end and discards the head, which is
    exactly the early narration dropped here, and it runs the minute the turn ends rather
    than in seven days. So what is dropped here is dropped for good as soon as a run is long
    enough, and runs this long are what motivated the change.
    """
    thoughts = _thoughts(said)
    return thoughts[-1] if thoughts else ""


def _handle(said: list) -> str | None:
    """Where the brain says the conversation got to, off the record that ends the turn."""
    for one in reversed(said):
        if one.get("type") == "done":
            handle = one.get("session")
            return handle if isinstance(handle, str) and handle else None
    return None


def _answered(said: list) -> bool:
    """Whether the person who asked got anything back.

    A file counts and a tool call does not. Something delivered is an answer even when
    nothing was typed about it; reading a file and thinking about it is work nobody
    receives. Whitespace is not an answer either — a surface posts nothing for it, so a
    turn that produced only whitespace is a turn that produced nothing.
    """
    for one in said:
        if one.get("type") == "file":
            return True
        if one.get("type") == "text" and str(one.get("text") or "").strip():
            return True
    return False


def _never_ran(said: list, result, resumed: bool) -> bool:
    """Whether a resumed brain handed this turn straight back without ever running it.

    Measured on a live gateway, twice in 82 minutes: a resumed session's first record was
    a notification left over from the *previous* session, and it ended the turn 14 ms
    later reporting `ok`, a usage record of four zeros, and nothing said at all. The
    prompt was never read, and the process exited zero — so nothing below rundesk could
    tell either, and the question was consumed.

    **Narrow on purpose, because the cost of being wrong is a brain asked to do the same
    work twice.** Every one of these has to hold, and each rules out a turn that failed
    for a reason a fresh session would meet again:

    - it was resumed — a turn that carried nothing on had no stale session to be given
      back, and starting it again would only repeat it;
    - the program finished and nothing it said was lost — a crash, a hole in the account
      or a cancelled turn is not a turn that never ran;
    - the brain said the turn ended, and said it ended well — no `done` at all is the
      shape a killed gateway leaves, and nothing here may declare such a turn over;
    - it classified nothing — a refusal, an exhausted account or a lost context is a
      decision the brain made, and it will make it again (R-RUN-19);
    - nobody was answered (R-RUN-21);
    - and it reported what it cost, and what it cost was nothing at all. Reported,
      because a brain that measures nothing says nothing about what happened and silence
      about cost is not evidence of a turn that never ran (R-USE-7); nothing at all,
      because one token in any of the four slots is a brain that reached the prompt.
    """
    if not resumed or not result.ok:
        return False
    if _ended(said) is not True or _because(said) is not None or _answered(said):
        return False
    tokens = _tokens(said)
    if not tokens.get("reported"):
        return False
    return not any(tokens.get(what) for what in ("input", "output", "cached", "written"))


def _why(said: list) -> str | None:
    """What the brain said went wrong, when it said anything at all.

    Off the record that ends the turn, because stderr is kept beside a run and not *in*
    it — so a turn that failed had its reason in a file nobody reads a run back from.
    """
    for one in reversed(said):
        if one.get("type") == "done":
            why = one.get("why")
            return why if isinstance(why, str) and why else None
    return None


#: The closed set of words for why a turn stopped (R-RUN-19). Short and shut on purpose: a
#: word a surface cannot phrase is a word nobody benefits from, and the point of the set is
#: that everything downstream knows every member of it.
#:
#: An adapter that cannot classify a failure says nothing, exactly as it already omits a
#: usage field it cannot measure — so this is additive, and no adapter that never learns any
#: of these behaves differently than it does today.
BECAUSE = ("rate_limited", "usage_exhausted", "no_credit", "signed_out",
           "context_exceeded", "cancelled", "refused", "crashed")


def _because(said: list) -> str | None:
    """Which of the closed words the brain gave for stopping, if it gave one at all.

    Off the record that ends the turn, like `why` beside it. A word this rundesk does not
    know is dropped rather than stored: the whole value of a closed set is that a reader can
    exhaust it, and one unknown member silently in the column takes that away — while an
    adapter reporting a word from a *newer* rundesk is exactly the case that must not corrupt
    an older one's totals.
    """
    for one in reversed(said):
        if one.get("type") == "done":
            word = one.get("because")
            return word if isinstance(word, str) and word in BECAUSE else None
    return None


def _ended(said: list) -> bool | None:
    """Whether the brain said the turn worked, or said nothing about it at all."""
    for one in reversed(said):
        if one.get("type") == "done":
            return bool(one.get("ok"))
    return None


def _tokens(said: list) -> dict:
    """What this turn cost, or that nobody said what it cost.

    A run whose usage never arrived says so rather than reporting a cost of nothing
    (R-USE-7): zero and unknown are different answers, and a spend limit that read the
    first for the second would never fire. What a brain reported is recorded as reported
    and never adjusted (R-USE-2) — the arithmetic that turns a conversation's running
    total into a turn's share belongs in the adapter, which is the only thing that knows
    its brain reports one. Cache writes are kept apart from cache reads because they are
    billed apart (R-USE-4) — and apart from fresh input too, for the same reason and in the
    other direction (R-USE-13): a write bills *above* standard input where a read bills at a
    fraction of it, so the three cannot share two slots without one of them being priced as
    something it is not.
    """
    counted = [one for one in said if one.get("type") == "usage"]
    if not counted:
        return {"reported": False}
    adding: dict = {"reported": True}
    # Only what was actually reported. A brain that cannot tell fresh tokens from cached
    # ones omits `cached`, and summing that into nothing would say it read nothing from
    # the cache — which is the same lie as a cost of nothing, one level down. What nobody
    # measured is absent here too.
    for what in ("input", "output", "cached", "written"):
        values = [one[what] for one in counted
                  if isinstance(one.get(what), int) and not isinstance(one.get(what), bool)]
        if values:
            adding[what] = sum(values)
    model = [one.get("model") for one in counted if one.get("model")]
    if model:
        # Only ever what a brain said actually answered. One that names none leaves none
        # claimed, rather than the one that happened to be asked for (R-PRV-9).
        adding["model"] = model[-1]
    return adding
