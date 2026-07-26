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

**Four records are rundesk's own** — `admitted`, `sent`, `outcome` and `lost` — and they
cannot be confused with a brain's, because a brain's six are the only ones the seam
understands: an adapter that emitted `admitted` would have it kept as a record nobody here
knows, exactly like any other.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass, field
from pathlib import Path

from rundesk import agent as agents
from rundesk import process, provider, store, transcript

#: What a conversation is called when nobody named one. A second `rundesk ask` carries the
#: first one on, which is what a person at a terminal means by asking again.
TERMINAL = "terminal"

#: Rundesk's own records in an account. Kept apart from the six a brain may report — not
#: by convention but by construction, since the seam understands only those six and would
#: keep one of these from an adapter as a record it does not know.
#: How many lines of what a brain said went wrong are carried back with the outcome. The
#: whole of it is in the run's own file; this is the tail worth putting in front of a person.
TROUBLE_KEPT = 20

ADMITTED = "admitted"
SENT = "sent"
OUTCOME = "outcome"
LOST = "lost"


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

    can = await provider.capabilities(at, provider.environment(
        home=whose["run"], cwd=whose["home"], provider_home=home, run="capabilities",
        posture=posture, path=None,
    ))
    kept = agents.records(name, where)
    where_it_is = kept.opened(store.conversation_id(on, conversation), on, kind,
                              conversation, _stamped(now))["id"]
    resume = None
    if can["resume"] and not fresh:
        resume = kept.session(where_it_is, brain)

    at_now = _stamped(now)
    if preface:
        # Written down as something *rundesk* said into the conversation, because a turn
        # that read standing instructions read something the person never typed — and an
        # account that does not show it cannot explain afterwards why it answered as it
        # did (R-RUN-9). `rundesk` is an author for exactly this.
        kept.arrived(where_it_is, at_now, preface, author="rundesk")
    # What was asked, written *before* the run that answers it — so the run says what
    # caused it (R-STO-10) rather than being linked to it afterwards, and so a turn that
    # died before it reached the brain still shows what somebody asked for.
    asked = kept.arrived(where_it_is, at_now, prompt,
                         who=(asked_by or {}).get("user") or None)
    run = kept.began(
        "channel" if asked_by else "terminal", named, brain, posture, at_now,
        conversation_id=where_it_is, trigger_message_id=asked, model=model, can=can,
        settings=settings, resumed=bool(resume), pick=pick,
    )
    if admitted is not None:
        admitted(run, dict(can))
    with _Account(kept, run, where_it_is, transcript.beside(whose["logs"], run),
                  now=now) as writing:
        # Written before the brain is started, because what is sent is what the account
        # has to show — and an account written afterwards is one that can be written to
        # match whatever happened. A steered turn records it as it sends it instead, so
        # that everything said mid-turn lands in the order it was said.
        #
        # **One gate, asked once.** This used to be decided here by what the brain can do
        # and again inside `_run` by whether the caller had anything to steer with. The two
        # look interchangeable right up until the caller has nothing to add — which is
        # every ordinary `rundesk ask` — and then the record was skipped here and never
        # written there, so a turn reached a brain with nothing in its account to show for
        # it (R-RUN-9, R-PRV-10).
        if not can["steer"]:
            writing.add(event={"type": SENT, "text": prompt})

        said: list = []
        # Kept as well as written down, so what went wrong can be shown to whoever asked.
        trouble: list = []
        program = process.Program(
            [str(at)],
            env=provider.environment(
                home=whose["run"], cwd=whose["home"], provider_home=home, run=run,
                model=model, resume=resume, posture=posture, settings=settings,
                raw=transcript.printed(whose["logs"], run), preface=preface,
            ),
            # **The agent's home, not its workspace.** A brain loads the rules it is to
            # follow because they *stand in the directory it stands in* — that is the whole
            # mechanism, and it is what the scaffolded `AGENTS.md` says out loud. Standing
            # it one directory lower put every one of those files out of its reach: the
            # agent was asked who it was and answered, truthfully, that there was nothing
            # here to tell it. `workspace/` is still where it works, by instruction, which
            # is what that file also says.
            cwd=whose["home"],
            takes_input=True,
            errors_apart=True,
            on_error=_noting(writing, trouble),
        )
        result = await _run(program, prompt, writing, said, watching,
                            steer=can["steer"], steering=steering)

        # Inside the same writer, and last. A second one would count from nothing and
        # give the end of a run the same places in the order as its beginning.
        handle = _handle(said)
        carried = bool(handle) and can["resume"]
        if carried:
            kept.remember_session(where_it_is, brain, handle)
        tokens = _tokens(said)
        ended = _ended(said)
        ok = result.ok and ended is not False
        # What the brain finally said, as one thing said in the conversation. Written at
        # the end because it is only whole then: a reply arrives a fragment at a time, and
        # a row per fragment is a history nobody can read back and a search that matches
        # half a sentence.
        writing.answered("".join(one.get("text", "") for one in said
                                 if one.get("type") == "text"))
        # How it finished, in one word. A turn is `finished` only when the program ended
        # well *and* the brain did not say otherwise — a brain that answered "no" through
        # a process that exited zero is a failed turn, and the two used to be told apart
        # by two fields that a reader had to combine correctly to get right.
        became = "finished" if ok else ("failed" if result.ok else result.reason)
        kept.ended(run, _stamped(now), became, exit_code=result.code,
                   why=_why(said), tokens=tokens)
    return Outcome(run=run, ok=ok, reason=result.reason, said=said, tokens=tokens,
                   handle=handle if carried else None, why=_why(said),
                   trouble=[one for one in trouble if one.strip()][-TROUBLE_KEPT:])


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
        """One thing that happened, added and never rewritten (R-RUN-5)."""
        self._seq += 1
        at = _stamped(self._now)
        kind = (event or {}).get("type")
        if kind == SENT:
            # The prompt is already a message: it was written before the run, because a
            # run has to say what caused it. What reaches here without `mid` *is* that
            # one. What reaches here with it is a word somebody said while the turn was
            # already running, which is a message of its own and belongs in the order it
            # was said (R-RUN-9).
            if event.get("mid"):
                self._kept.arrived(self._conversation, at, str(event.get("text") or ""))
            return self._seq
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
            self._kept.answered(self._conversation, self.run, _stamped(self._now), text)

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


def _stamped(now=None) -> str:
    """Wall time, for a person reading it back. Never what anything is ordered by (R-RUN-7).

    The clock is the caller's, so a case fixes it and every record of that turn agrees.
    """
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime((now or time.time)()))


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
               steer: bool = False, steering=None) -> process.Result:
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
            writing.add(event={"type": SENT, "text": word, "mid": True})
            await program.send(provider.spoken(word))
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


def _handle(said: list) -> str | None:
    """Where the brain says the conversation got to, off the record that ends the turn."""
    for one in reversed(said):
        if one.get("type") == "done":
            handle = one.get("session")
            return handle if isinstance(handle, str) and handle else None
    return None


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
    billed apart (R-USE-4).
    """
    counted = [one for one in said if one.get("type") == "usage"]
    if not counted:
        return {"reported": False}
    adding: dict = {"reported": True}
    # Only what was actually reported. A brain that cannot tell fresh tokens from cached
    # ones omits `cached`, and summing that into nothing would say it read nothing from
    # the cache — which is the same lie as a cost of nothing, one level down. What nobody
    # measured is absent here too.
    for what in ("input", "output", "cached"):
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
