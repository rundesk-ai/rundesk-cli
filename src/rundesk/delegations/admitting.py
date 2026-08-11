"""Whether one agent may hand this work to another, and writing it down when it may.

Everything refusable is refused **before** anything durable is written, and the row is written last.
A delegation half-admitted is the shape that leaves an agent believing it handed work over when
nothing will ever answer.

## The two guards, and why there is no chain

The previous build carried an array of everyone the work had passed through, so a cycle could be
refused by naming the path. It needed one because its depth rule was inconsistent — onward
delegation was legal on the delegation path and refused outright on the role path, *"two answers to
one question."*

Held to uniformly, **depth one makes a cycle unconstructible**: an agent answering a delegation is
never shown a team to hand work to, and is refused here if it tries anyway, so `ava → bob → ava` has
no path to exist. What is left is two checks that read only the turn in front of them:

1. An agent may not delegate to itself. That is a turn, not a delegation.
2. A turn that is itself answering a delegation may not delegate.

Both are cheap, and neither has to walk anything.

## Who is asking is read from the environment, and it is not a security boundary

`RUNDESK_AGENT` and `RUNDESK_RUN` are set by the gateway when it starts a brain, so a command run
from inside a turn knows whose turn it is. A brain determined to get around that can clear a
variable — this is a **correctness guard, not a security boundary**, and it is worth saying out loud
because the previous build's docstring said the same thing and somebody still has to not assume
otherwise. What it prevents is an honest mistake, not an attack; an agent already has the owner's
shell.

May depend on `agents`, `core` and `utils`.
"""

import os
import secrets
from typing import Callable, Optional

from rundesk.delegations import kept

#: What the gateway tells a turn about itself. Read rather than passed, because the command runs in a
#: process the turn started and there is nothing to pass it through.
AGENT = "RUNDESK_AGENT"
RUN = "RUNDESK_RUN"

#: Set on a turn that is itself answering a delegation, so a command run from inside one can tell.
#: The second guard is the whole reason it exists.
ANSWERING = "RUNDESK_DELEGATION"

#: How long a task may be. Generous — a brief is often several paragraphs — and bounded, because it
#: is written into another agent's records and an agent's memory is not somewhere to be filled from
#: outside.
A_TASK_AT_MOST = 16 * 1024


#: What a delegation is called, in front of a person and in every command that takes one.
#: `del-<the turn that asked>-<a short mark>` — the turn makes it readable and roughly ordered, and
#: the mark is what keeps two delegations from one turn apart. Uniqueness is the column's, not this
#: function's: `delegation_id` is `UNIQUE`, so a collision is refused rather than merged.
NAMED = "del-{parent_turn}-{mark}"

#: How much of a random mark is used. Six hex characters inside one turn is not a birthday problem
#: anybody will meet, and a long id is one nobody can read back over a terminal.
MARK_CHARACTERS = 6


class Refused(Exception):
    """Why this work may not be handed over, said as the thing somebody did."""


class Asking:
    """Whose turn is doing the asking, and what it is answering.

    Built from the environment by `whoever_is_asking`, or by hand in a case. A value object rather
    than four reads scattered about, because every guard below needs the same three facts and a
    caller that read one of them differently would be a caller with its own idea of who is asking.
    """

    def __init__(self, agent: Optional[str], run: Optional[int], answering: Optional[str] = None):
        self.agent = agent
        self.run = run
        self.answering = answering

    @property
    def is_a_turn(self) -> bool:
        """Whether this is an agent's own turn rather than somebody at a terminal."""
        return bool(self.agent and self.run)


def whoever_is_asking(said: Optional[dict] = None) -> Asking:
    """Who is running this command, read off the environment.

    `said` is the environment to read, and it is an argument so a case can hand one in — the whole
    of this module is otherwise untestable without starting a real turn.
    """
    values = os.environ if said is None else said
    run = values.get(RUN)
    return Asking(agent=values.get(AGENT) or None,
                  run=int(run) if run and str(run).isdigit() else None,
                  answering=values.get(ANSWERING) or None)


def a_name(parent_turn: int, marking: Optional[Callable[[], str]] = None) -> str:
    """What to call this delegation.

    `marking` is how the short mark is produced, and it is an argument so a case can hand in one
    that does not change between runs. **Resolved inside the body** rather than bound in the
    signature: a default bound at definition is decided once, when the module is imported, and
    nothing can reach past it.
    """
    mark = (marking or (lambda: secrets.token_hex(MARK_CHARACTERS // 2)))()
    return NAMED.format(parent_turn=parent_turn, mark=mark)


def refusal(asking: Asking, to_agent: str, task: str,
            nothing_would_answer: bool = False, outside_scope: bool = False) -> str:
    """Why this delegation may not be admitted, or `""` when it may.

    A sentence rather than an exception, because the caller is a command whose job is to tell
    somebody what to type instead — and because the same answer is wanted before anything is
    written and never again.

    `nothing_would_answer` is decided by the layer that may reach `gateways`, and it is named for
    the decision rather than for the state on purpose. `standing.Standing` has no `online` shortcut
    and says why — *"a boolean would answer `False` both for a gateway that is not running and for
    one nobody could ask about, and telling those apart is the whole point of the type."* So the
    three answers are collapsed **where all three are visible**, and only a definite `OFFLINE`
    becomes `True`: refusing on uncertainty is the worse of the two errors.
    """
    if not asking.is_a_turn:
        return ("only an agent's own turn can hand work to another agent — "
                "this is how one agent asks another, not how a person does")
    if to_agent == asking.agent:
        return f"{asking.agent} cannot hand work to itself — that is a turn, not a delegation"
    if asking.answering:
        return (f"this turn is answering {asking.answering}, and work handed over cannot be handed "
                "on again — finish it here, or report that you are blocked")
    if not task.strip():
        return "there was nothing to hand over"
    if len(task) > A_TASK_AT_MOST:
        return (f"a task goes in at most {A_TASK_AT_MOST} characters, and this is {len(task)}")
    if outside_scope:
        return f"{asking.agent} is not configured to delegate to {to_agent}"
    if nothing_would_answer:
        return (f"{to_agent} has no gateway running, so nothing would ever answer this — "
                f"start it with: rundesk gateways start {to_agent}")
    return ""


def admitted(asking: Asking, delegation_id: str, to_agent: str,
             parent_conversation: int,
             provider_name: Optional[str] = None,
             model_name: Optional[str] = None) -> None:
    """Write the delegation down, in the **asking** agent's own store.

    Called only after `refusal` answered nothing, and it does not check again: two places deciding
    whether something is allowed is two places that can come to disagree, and the one that runs
    second is the one nobody reads.
    """
    if not asking.agent or not asking.run:
        raise Refused("a delegation is written down by a turn, and this is not one")
    kept.made(
        asking.agent, delegation_id, to_agent, parent_conversation, asking.run,
        provider_name=provider_name, model_name=model_name)
