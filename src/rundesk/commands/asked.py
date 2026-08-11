"""What this agent has handed to other agents, and the three things it can do about one.

**The half of delegating that is not `ask`.** An agent that hands work over is told the id once, at
the moment it does it — and a turn is not a place anything is remembered. So without this there is
no way back to a delegation: nothing to list, nothing to carry on, and an id somebody would have to
have written down.

## Who is asking is read, never typed

Every verb here works on **this agent's own** delegations, and which agent that is comes from the
environment the gateway set — the same `RUNDESK_AGENT` `ask` reads. A person at a terminal has no
turn, so they name one with `--agent`. Nothing else is ever named: an agent typing its own name
would be an agent that could type somebody else's.

## Three verbs, because there are three things to mean

`say` puts words into work that is still going. `stop` ends it. `resume` carries answered work on;
stopped work stays closed.
A single verb guessing from the state would say something into work in flight when the agent meant
to start it again, and spend a brain's time doing it — so each refuses in the other's case and names
the one that was wanted.

**`say` and `resume` are the same act underneath**, and deliberately not folded together: both put a
message into the conversation the work is happening in, and the answering agent's own gateway takes
it from there. What differs is only which state each is willing to do it in, which is exactly the
thing a person gets wrong and wants told about.

**`say` is durable before it is live.** This command writes the words into the answering agent's
conversation. Its gateway, which owns the in-process provider turn, steers them into that turn while
it is still accepting input. The message is claimed by that turn before it enters the live queue;
if the provider refuses it or the race was already lost, the claim is released or never made and
the next turn reads it. That ordering is what makes guidance neither lost nor delivered twice.
"""

import argparse

from rundesk.agents import directory, records
from rundesk.channels import arriving
from rundesk.commands import Subcommands, failed
from rundesk.core import paths
from rundesk.delegations import admitting
from rundesk.delegations import kept as delegations
from rundesk.exits import OK
from rundesk.utils import locking
from rundesk.utils.terminal import as_table

#: Everything reading or changing a delegation can end as. `NotThere` is here because a delegation
#: nobody made and an agent nobody made arrive the same way to somebody who mistyped an id.
TROUBLE = (delegations.Refused, directory.Refused, records.NotThere, records.Unreadable,
           locking.Stuck, OSError)


def register(sub: Subcommands) -> None:
    """One verb, three sub-verbs, and a listing when none is named."""
    said = sub.add_parser("asked", help="what this agent has handed to other agents")
    said.add_argument("--agent", metavar="<agent>", default=None,
                      help="whose delegations — needed only outside a turn, which knows already")
    what = said.add_subparsers(dest="what", metavar="<what>")

    shown = what.add_parser("show", help="one delegation in full")
    shown.add_argument("delegation", metavar="<id>")

    saying = what.add_parser(
        "say", help="steer work that is still going; fall back to its next turn if missed")
    saying.add_argument("delegation", metavar="<id>")
    saying.add_argument("words", metavar="<words>", nargs="+")

    ending = what.add_parser("stop", help="ask for work to end before it finishes")
    ending.add_argument("delegation", metavar="<id>")

    carrying = what.add_parser("resume", help="carry a finished one on, in the session it had")
    carrying.add_argument("delegation", metavar="<id>")
    carrying.add_argument("words", metavar="<words>", nargs="+", help="what more to do")


def cmd_asked(args: argparse.Namespace) -> int:
    """A `Namespace` in, an exit code out."""
    agent = args.agent or admitting.whoever_is_asking().agent
    if not agent:
        return _failed("there is no turn here, so nobody is asking",
                       "name whose delegations to look at with: rundesk asked --agent <agent>")
    trouble = directory.not_an_agent(agent)
    if trouble:
        return _failed(trouble, "see what there is with: rundesk agents")

    what = getattr(args, "what", None)
    try:
        if what is None:
            return _listed(agent)
        if what == "show":
            return _shown(agent, args.delegation)
        if what == "say":
            return _said_into(agent, args.delegation, " ".join(args.words))
        if what == "stop":
            return _stopped(agent, args.delegation)
        if what == "resume":
            return _carried_on(agent, args.delegation, " ".join(args.words))
    except TROUBLE as why:
        return _failed(str(why))

    raise AssertionError(f"asked {what} is registered on the parser and answered by nothing")


def _listed(agent: str) -> int:
    """Everything this agent has handed over, newest first, and what each is waiting on.

    **Says where it is looking even when there is nothing**, like every other listing here: an
    agent told nothing at all cannot tell "none" from "this command did not work".
    """
    every = delegations.every(agent)
    print(f"what {agent} has handed to other agents")
    if not every:
        print("        nothing yet — hand something over with: rundesk ask <agent> \"<the task>\"")
        return OK
    as_table(["ID", "TO", "STATE", "ASKED"],
             [[one.delegation_id, one.to_agent, _how(one), one.created_at] for one in every])
    return OK


def _shown(agent: str, delegation_id: str) -> int:
    """One delegation, in full."""
    one = delegations.one(agent, delegation_id)
    as_table(["WHAT", "IS"],
             [["id", one.delegation_id],
              ["handed to", one.to_agent],
              ["state", _how(one)],
              ["provider requested", one.requested_provider_name or "target default"],
              ["model requested", one.requested_model_name or "provider default"],
              ["provider effective", one.provider_name or "resolved from target at claim"],
              ["model effective", one.model_name or "provider/configured default at claim"],
              ["asked at", one.created_at],
              ["last change", one.latest_at],
              ["answered at", one.answered_at or "not yet"],
              ["stopped at", one.stopped_at or "not stopped"],
              ["stop asked at", one.stop_asked_at or "nobody has"]])
    print(f"        what was said:  rundesk messages {one.to_agent} --source agent")
    return OK


def _said_into(agent: str, delegation_id: str, words: str) -> int:
    """Durably guide work; its gateway steers the active turn or leaves it for the next one.

    This process cannot touch the target gateway's in-memory turn. Writing first makes the gateway's
    next pass the bridge without making process timing a delivery guarantee.
    """
    if not words.strip():
        return _failed("there was nothing to say")
    # Collection reads the answering agent and then settles the delegator's row. Hold the install's
    # existing state-change lock across this opposite two-store move, so either guidance lands
    # before collection decides or collection finishes and this is refused — never an orphaned
    # message behind a row the gateway has already settled.
    with locking.only_one(paths.lock(), f"guidance for {delegation_id}"):
        one = delegations.one(agent, delegation_id)
        if one.answered_at or one.stopped_at:
            return _failed(
                f"{delegation_id} is already {_how(one)}, so there is no work to say this into",
                *([f"carry it on instead with: rundesk asked resume {delegation_id} \"<what more>\""]
                  if one.answered_at else []))
        arriving.recorded_for_a_delegation(
            one.to_agent, agent, one.parent_turn, words, delegation_id=delegation_id,
            legacy_fallback=True)
        # **The message first, the moment second**, and inside the same lock. The row is what the
        # asking agent's gateway watches to tell its room the work was updated, and what the
        # retention window is counted from — so guidance that moved neither would be words nobody
        # is shown, on a delegation that ages as though nobody had been near it. Stamped after the
        # message so a crash between the two leaves guidance waiting rather than a moment that
        # claims words which were never written.
        delegations.guided(agent, delegation_id)
    print(f"added to {delegation_id}  ·  active-first: {one.to_agent}'s gateway offers it now; "
          "if missed or refused, its next turn reads it")
    return OK


def _stopped(agent: str, delegation_id: str) -> int:
    """Ask for work to end.

    **A request, and never an outcome.** What became of the work is the turn's to say, and this
    reports what it did — asked for a stop — rather than claiming the work has ended.
    """
    one = delegations.one(agent, delegation_id)
    if not delegations.stop_asked(agent, delegation_id):
        return _failed(
            f"{delegation_id} is already over, so there was nothing to stop"
            if one.answered_at or one.stopped_at
            else f"a stop has already been asked for on {delegation_id}")
    print(f"a stop was asked for on {delegation_id}")
    return OK


def _carried_on(agent: str, delegation_id: str, words: str) -> int:
    """Carry an answered delegation on, with more to do.

    **The same conversation, so the same provider session.** The answering agent picks up where it
    left off rather than being handed a second task that repeats the first — which is the whole
    difference between resuming and asking again.
    """
    one = delegations.one(agent, delegation_id)
    if not words.strip():
        return _failed("carrying one on needs something more to do")
    if one.stopped_at:
        return _failed(f"{delegation_id} was stopped and cannot be carried on",
                       "hand over a new delegation if more work is wanted")
    if not one.answered_at:
        return _failed(f"{delegation_id} is still being answered, so there is nothing to carry on",
                       f"say something into it instead with: "
                       f"rundesk asked say {delegation_id} \"<words>\"")
    # **The message first, the reopening second**, the same order and for the same reason as
    # `ask._handed_over`: reopened first, the answering gateway could pick the work up on its next
    # beat and find nothing new to answer. Interrupted between the two, what is left is a message in
    # a settled conversation that nothing acts on — while the reverse would leave the delegation
    # reopened and waiting on a further task that was never written.
    arriving.recorded_for_a_delegation(
        one.to_agent, agent, one.parent_turn, words, delegation_id=delegation_id,
        legacy_fallback=True)
    delegations.reopened(agent, delegation_id)
    print(f"{delegation_id} carried on  ·  {one.to_agent} takes it up in the session it had")
    return OK


def _how(one: delegations.Delegation) -> str:
    """What state a delegation is in, read off what has happened to it rather than kept.

    Three words, and each is a different thing to do next: `working` is somebody else's turn to
    finish, `stopping` is a request nothing has acted on yet, and `answered` is this agent's to
    review or carry on.
    """
    if one.stopped_at:
        return "stopped"
    if one.answered_at:
        return "answered"
    return "stopping" if one.stop_asked_at else "working"


def _failed(why: str, *and_so: str) -> int:
    return failed(f"asked: FAILED — {why}", *and_so)
