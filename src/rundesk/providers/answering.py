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
import json
import threading
from pathlib import Path
from typing import Callable, Optional

from rundesk.agents import directory
from rundesk.channels import arriving, delivery, hosting
from rundesk.channels import kept as channels_kept
from rundesk.core import config
from rundesk.providers import instructions, kept, protocol, turns
from rundesk.schedules import due, firing
from rundesk.schedules import kept as schedules_kept
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

    def answer(self, agent: str, kind: str, place: str, who: str, body: str,
               external_id: Optional[str], landed: arriving.Landed) -> None:
        """Start a turn for this message and **return at once**. Never raises.

        A thread rather than the caller's, for the reason `hosting.Answering` gives. Daemon, because
        a gateway going down must not be held open by a turn — what settles that turn is the same
        thing that settles one killed outright, and it is the lock rather than this thread.
        """
        answering = threading.Thread(
            target=self._answered, name=f"answer-{kind}-{place}",
            args=(agent, kind, place, body, landed), daemon=True)
        answering.start()

    def _answered(self, agent: str, kind: str, place: str, body: str,
                  landed: arriving.Landed) -> None:
        """One turn for one message. **Never raises** — this is a thread, and nobody is above it."""
        try:
            self._marked(agent, kind, place, WORKING)
            got = turns.run(turns.Request(
                agent=agent, prompt=body, conversation=landed.conversation,
                trigger=instructions.A_PERSON_ASKED,
                source=arriving.FROM_CHANNEL, place=place))
            self._delivered(agent, kind, place, got)
            self._marked(agent, kind, place, AS_A_STATE.get(got.turn_status, FAILED))
        except turns.Busy:
            # Something is already answering in this conversation. Not a failure and not a second
            # turn: the person will get the answer to what they asked a moment ago.
            _note(self._where, f"channel {kind}: {place} is already being answered, so this was "
                               "recorded and not answered again")
        except Exception as why:                       # noqa: BLE001 — see the docstring
            _note(self._where, f"channel {kind}: answering {place} went wrong ({why})", logs.ERROR)
            with contextlib.suppress(Exception):
                self._marked(agent, kind, place, FAILED)

    def _delivered(self, agent: str, kind: str, place: str, got: turns.Outcome) -> None:
        """The answer, cut to what this platform takes, with whatever the brain made beside it."""
        said = got.reply.strip() or self._instead(got)
        if not said:
            return
        carrying = delivery.carried(agent, [str(one.get("at")) for one in got.files
                                            if one.get("at")])
        pieces = delivery.split(said, at_most=self._at_most(agent, kind))
        hosting.told(agent, self._where, self._hosted(), kind, place, pieces,
                     sending=carrying.files)

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

    def _marked(self, agent: str, kind: str, place: str, state: str) -> None:
        """Say what the turn is doing, in the words the channel layer renders. Never raises."""
        hosting.marked(agent, self._where, self._hosted(), kind, place, state)


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


def _note(where: Path, said: str, level: str = logs.INFO) -> None:
    """One line in the gateway's own log, and never a reason to end anything."""
    with contextlib.suppress(Exception):
        if where.parent.is_dir():
            logs.note(where, said, level)
