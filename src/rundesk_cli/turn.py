"""One turn: what it resolved, what it ran, and the account it left behind.

The only module that knows the others exist. `provider` is the seam, `transcript` is the
account and `session` is where a conversation got to — each of them is about one thing and
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
from dataclasses import dataclass, field
from pathlib import Path

from rundesk_cli import agent as agents
from rundesk_cli import process, provider, session, transcript

#: What a conversation is called when nobody named one. A second `rundesk ask` carries the
#: first one on, which is what a person at a terminal means by asking again.
TERMINAL = "terminal"

#: Rundesk's own records in an account. Kept apart from the six a brain may report — not
#: by convention but by construction, since the seam understands only those six and would
#: keep one of these from an adapter as a record it does not know.
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
    fresh: bool = False,
    watching=None,
    root: Path | None = None,
    now=None,
    pick=None,
) -> Outcome:
    """Run one turn for this agent, and write down everything about it.

    `named` is the brain as the owner named it — a shipped adapter or a path to a program
    — and it is carried through rather than looked up in any list. `watching` is handed
    each record as it arrives, for a terminal that is showing the turn as it happens; the
    account is written whether or not anyone is watching.
    """
    at = provider.program(named)          # raises NotRunnable, before anything is written
    whose = agents.paths(name, where)
    brain = provider.key(named)
    home = agents.provider_home(name, brain, where)
    home.mkdir(parents=True, exist_ok=True)
    whose["runs"].mkdir(parents=True, exist_ok=True)

    can = await provider.capabilities(at, provider.environment(
        home=whose["run"], cwd=whose["workspace"], provider_home=home, run="capabilities",
        posture=posture, path=None,
    ))
    resume = None
    if can["resume"] and not fresh:
        resume = session.of(whose["agent"], brain, conversation)

    run = transcript.allocate(whose["runs"], pick=pick)
    with transcript.Writer(whose["runs"], run, name, now=now) as writing:
        writing.add(event={
            "type": ADMITTED, "provider": named, "brain": brain, "posture": posture,
            "conversation": conversation, "model": model, "resumed": bool(resume),
            "settings": dict(settings or {}), "can": can,
        })
        # Written before the brain is started, because what is sent is what the account
        # has to show — and an account written afterwards is one that can be written to
        # match whatever happened.
        writing.add(event={"type": SENT, "text": prompt})

        said: list = []
        program = process.Program(
            [str(at)],
            env=provider.environment(
                home=whose["run"], cwd=whose["workspace"], provider_home=home, run=run,
                model=model, resume=resume, posture=posture, settings=settings,
            ),
            cwd=whose["workspace"],
            takes_input=True,
            errors_apart=True,
            on_error=writing.went_wrong,
        )
        result = await _run(program, prompt, writing, said, watching)

        # Inside the same writer, and last. A second one would count from nothing and
        # give the end of a run the same places in the order as its beginning.
        handle = _handle(said)
        kept = bool(handle) and can["resume"] and session.remember(
            whose["agent"], brain, conversation, handle)
        tokens = _tokens(said)
        ended = _ended(said)
        ok = result.ok and ended is not False
        writing.add(event={
            "type": OUTCOME, "ok": ok, "reason": result.reason, "code": result.code,
            "tokens": tokens, "kept": kept if handle else None,
            "lost": result.undelivered,
        })
    return Outcome(run=run, ok=ok, reason=result.reason, said=said, tokens=tokens,
                   handle=handle if kept else None)


async def _run(program, prompt: str, writing, said: list, watching) -> process.Result:
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
    try:
        await program.send(prompt.encode("utf-8"))
        await program.close_input()
    except process.NotListening:
        pass  # a brain that answered and left before we finished writing is not a failure
    return await reading


def _handle(said: list) -> str | None:
    """Where the brain says the conversation got to, off the record that ends the turn."""
    for one in reversed(said):
        if one.get("type") == "done":
            handle = one.get("session")
            return handle if isinstance(handle, str) and handle else None
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
    adding = {"reported": True, "input": 0, "output": 0, "cached": 0}
    for one in counted:
        for what in ("input", "output", "cached"):
            value = one.get(what)
            if isinstance(value, int) and not isinstance(value, bool):
                adding[what] += value
    model = [one.get("model") for one in counted if one.get("model")]
    if model:
        # Only ever what a brain said actually answered. One that names none leaves none
        # claimed, rather than the one that happened to be asked for (R-PRV-9).
        adding["model"] = model[-1]
    return adding
